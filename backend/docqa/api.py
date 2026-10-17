import hashlib

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alphabacktest.auth import current_user

from . import config, db, pipeline, providers
from .models import Chunk, Document
from .storage import document_prefix, get_storage

router = APIRouter(prefix="/api/docqa", tags=["docqa"])


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": code, "message": message})


def require_enabled() -> None:
    if not config.enabled():
        raise _error(503, "docqa_disabled", "Document Q&A is not set up on this server.")


def user_id(user=Depends(current_user)) -> int:
    return user.id


class DocumentOut(BaseModel):
    id: int
    filename: str
    status: str
    error: str | None
    pageCount: int
    chunkCount: int
    sizeBytes: int
    createdAt: str
    embeddingModel: str | None
    chunkWords: int | None
    chunkOverlap: int | None
    pdfTitle: str | None
    pdfAuthor: str | None
    pdfCreated: str | None
    stale: bool   # made with a different embedding model than the server uses now, so it is skipped in searches


def _out(d: Document) -> DocumentOut:
    return DocumentOut(id=d.id, filename=d.filename, status=d.status, error=d.error, pageCount=d.page_count,
                       chunkCount=d.chunk_count, sizeBytes=d.size_bytes, createdAt=d.created_at.isoformat(),
                       embeddingModel=d.embedding_model, chunkWords=d.chunk_words, chunkOverlap=d.chunk_overlap,
                       pdfTitle=d.pdf_title, pdfAuthor=d.pdf_author, pdfCreated=d.pdf_created,
                       stale=d.status == "ready" and d.embedding_model != config.current_embedding_model())


@router.get("/config")
def get_config():
    return {"enabled": config.enabled(), "minScore": config.min_rerank_score(),
            "chunkWords": config.CHUNK_WORDS, "chunkOverlap": config.CHUNK_OVERLAP_WORDS,
            "minChunkWords": config.MIN_CHUNK_WORDS, "maxChunkWords": config.MAX_CHUNK_WORDS,
            "topK": config.DEFAULT_TOP_K, "maxTopK": config.MAX_TOP_K}


@router.get("/models", dependencies=[Depends(require_enabled)])
def list_models(uid: int = Depends(user_id)):
    """Models the answer can be written with, from Google's model list for this server's key."""
    try:
        models = providers.list_generation_models()
    except providers.ProviderError as e:
        raise _error(503, "model_unavailable", str(e))
    return {"default": config.generation_model(), "models": models}


@router.get("/documents", response_model=list[DocumentOut], dependencies=[Depends(require_enabled)])
def list_documents(uid: int = Depends(user_id), s: Session = Depends(db.get_db)):
    rows = s.scalars(select(Document).where(Document.user_id == uid).order_by(Document.created_at.desc()))
    return [_out(d) for d in rows]


@router.post("/documents", response_model=DocumentOut, status_code=202, dependencies=[Depends(require_enabled)])
def upload(file: UploadFile, background: BackgroundTasks,
                 chunk_words: int | None = Form(None, alias="chunkWords"),
                 chunk_overlap: int | None = Form(None, alias="chunkOverlap"),
                 uid: int = Depends(user_id), s: Session = Depends(db.get_db)):
    size = chunk_words if chunk_words is not None else config.CHUNK_WORDS
    overlap = chunk_overlap if chunk_overlap is not None else min(config.CHUNK_OVERLAP_WORDS, size // 2)
    if not config.MIN_CHUNK_WORDS <= size <= config.MAX_CHUNK_WORDS:
        raise _error(400, "bad_chunk_size", f"Chunk size must be between {config.MIN_CHUNK_WORDS} and {config.MAX_CHUNK_WORDS} words.")
    if not 0 <= overlap <= size // 2:
        raise _error(400, "bad_overlap", f"Overlap must be between 0 and half the chunk size ({size // 2} words).")
    name = (file.filename or "document.pdf").rsplit("/", 1)[-1][:300]
    if not name.lower().endswith(".pdf"):
        raise _error(400, "unsupported_type", "Only PDF files are supported for now.")
    data = file.file.read(config.MAX_FILE_BYTES + 1)   # a plain def runs in the thread pool, so reading and hashing do not block the server
    if len(data) > config.MAX_FILE_BYTES:
        raise _error(413, "too_large", f"The file is larger than {config.MAX_FILE_BYTES // (1024 * 1024)} MB.")
    if not data.startswith(b"%PDF"):
        raise _error(400, "not_a_pdf", "This file is not a PDF.")
    digest = hashlib.sha256(data).hexdigest()
    same = s.scalar(select(Document).where(Document.user_id == uid, Document.file_hash == digest))
    if same is not None:
        if (same.status == "ready" and same.embedding_model == config.current_embedding_model()
                and (same.chunk_words, same.chunk_overlap) == (size, overlap)):
            raise _error(409, "duplicate", f"You already uploaded this file as \"{same.filename}\" with the same chunk settings.")
        if same.status == "processing":
            raise _error(409, "already_processing", f"\"{same.filename}\" is still being processed. Wait for it to finish.")
        # A failed, out-of-date, or differently chunked copy of the same file: replace it.
        s.delete(same)
        s.commit()
        pipeline.delete_document_files(uid, same.id)
    count = s.scalar(select(func.count()).select_from(Document).where(Document.user_id == uid))
    if count >= config.MAX_DOCS_PER_USER:
        raise _error(409, "too_many", f"You can keep up to {config.MAX_DOCS_PER_USER} documents. Delete one first.")

    doc = Document(user_id=uid, filename=name, file_type="pdf", size_bytes=len(data), file_hash=digest,
                   chunk_words=size, chunk_overlap=overlap)
    s.add(doc)
    try:
        s.flush()
    except IntegrityError:   # the same file arrived twice at once
        s.rollback()
        raise _error(409, "duplicate", "You already uploaded this file.")
    doc.storage_key = f"{document_prefix(uid, doc.id)}/original.pdf"
    get_storage().put(doc.storage_key, data)
    s.commit()
    background.add_task(pipeline.ingest, doc.id)
    return _out(doc)


@router.post("/documents/{document_id}/reprocess", response_model=DocumentOut, status_code=202,
             dependencies=[Depends(require_enabled)])
def reprocess_document(document_id: int, background: BackgroundTasks, uid: int = Depends(user_id),
                       s: Session = Depends(db.get_db)):
    """Rebuild a document's passages from the stored PDF with the current processing, keeping its chunk settings.
    For out-of-date (stale) and failed documents, so they need not be uploaded again."""
    doc = s.get(Document, document_id)
    if doc is None or doc.user_id != uid:
        raise _error(404, "not_found", "Document not found.")
    if doc.status == "processing":
        raise _error(409, "already_processing", "This document is already being processed.")
    try:
        get_storage().get(doc.storage_key)
    except OSError:
        raise _error(409, "file_missing", "The original file is no longer stored. Delete this document and upload it again.")
    s.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    doc.status, doc.error, doc.chunk_count = "processing", None, 0
    s.commit()
    background.add_task(pipeline.ingest, doc.id)
    return _out(doc)


@router.delete("/documents/{document_id}", status_code=204, dependencies=[Depends(require_enabled)])
def delete_document(document_id: int, uid: int = Depends(user_id), s: Session = Depends(db.get_db)):
    doc = s.get(Document, document_id)
    if doc is None or doc.user_id != uid:
        raise _error(404, "not_found", "Document not found.")
    s.delete(doc)
    s.commit()
    pipeline.delete_document_files(uid, document_id)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    documentIds: list[int] | None = None   # omitted = all of the user's documents; an empty list is an error
    topK: int = Field(default=config.DEFAULT_TOP_K, ge=1, le=config.MAX_TOP_K)
    candidates: int = Field(default=config.DEFAULT_CANDIDATES, ge=1, le=config.MAX_CANDIDATES)
    rerank: bool = True
    # Drop reranked results scoring below this. Leave it out for the server default; send null for no cutoff.
    minScore: float | None = None
    generate: bool = False
    model: str | None = None   # Gemini model for the answer; None = the server default. Must be one of GET /models
    hybrid: bool = True   # also run a keyword (BM25) search and merge it with the vector results


class ChunkOut(BaseModel):
    chunkId: int
    documentId: int
    filename: str
    page: int
    section: str | None
    text: str
    rank: int                    # position in the "before reranking" list
    vectorRank: int | None       # None when the vector search did not return it (found by keywords only)
    vectorScore: float
    keywordRank: int | None      # None when the keyword search did not return it
    keywordScore: float | None
    rerankRank: int | None
    rerankScore: float | None


class AskOut(BaseModel):
    answer: str | None
    answerError: str | None      # why generation failed; the passages are still returned
    candidates: list[ChunkOut]   # before reranking: vector order
    chunks: list[ChunkOut]       # the final top_k (reranked when rerank is on), after the relevance cutoff
    droppedBelowCutoff: int      # how many of the top_k were removed for scoring below the cutoff
    minScore: float | None       # the cutoff that was applied


def _chunk(h: pipeline.Hit) -> ChunkOut:
    return ChunkOut(chunkId=h.chunk_id, documentId=h.document_id, filename=h.filename, page=h.page, section=h.section, text=h.text,
                    rank=h.rank, vectorRank=h.vector_rank, vectorScore=h.score,
                    keywordRank=h.keyword_rank, keywordScore=h.keyword_score, rerankRank=h.rerank_rank, rerankScore=h.rerank_score)


@router.post("/ask", response_model=AskOut, dependencies=[Depends(require_enabled)])
def ask(body: AskIn, uid: int = Depends(user_id), s: Session = Depends(db.get_db)):
    question = body.question.strip()
    if not question:
        raise _error(400, "empty_question", "Type a question first.")
    if body.documentIds is not None:
        if not body.documentIds:
            raise _error(400, "no_documents", "Select at least one document to search.")
        usable = s.scalar(select(func.count()).select_from(Document).where(
            Document.id.in_(body.documentIds), Document.user_id == uid, Document.status == "ready",
            Document.embedding_model == config.current_embedding_model()))
        if not usable:   # deleted, still processing, stale or not theirs: say so instead of returning "no passages"
            raise _error(400, "no_searchable_documents",
                         "None of the selected documents can be searched (deleted, still processing, or out of date). Refresh the list.")
    model = None
    if body.generate and body.model and body.model != config.generation_model():
        # The name goes into the URL we call, so accept only names Google itself listed for this key.
        try:
            allowed = {m["id"] for m in providers.list_generation_models()}
        except providers.ProviderError as e:
            raise _error(503, "model_unavailable", str(e))
        if body.model not in allowed:
            raise _error(400, "bad_model", "That model is not available. Pick one from the list.")
        model = body.model
    try:
        found = pipeline.retrieve(s, uid, question, body.documentIds, max(body.candidates, body.topK), body.hybrid)
        by_vector = list(found)
        final = pipeline.rerank(question, found) if body.rerank else found
        final = final[:body.topK]
        cutoff = body.minScore if "minScore" in body.model_fields_set else config.min_rerank_score()
        dropped = 0
        if body.rerank and cutoff is not None:
            kept = [h for h in final if h.rerank_score >= cutoff]
            dropped, final = len(final) - len(kept), kept
    except providers.ProviderError as e:
        raise _error(503, "model_unavailable", str(e))
    text = answer_error = None
    if body.generate and final:   # nothing relevant: don't spend a model call
        try:
            text = pipeline.answer(question, final, model)
        except providers.ProviderError as e:
            answer_error = str(e)
    return AskOut(answer=text, answerError=answer_error, candidates=[_chunk(h) for h in by_vector], chunks=[_chunk(h) for h in final],
                  droppedBelowCutoff=dropped, minScore=cutoff if body.rerank else None)
