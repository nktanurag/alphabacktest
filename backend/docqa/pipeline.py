import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import bm25, chunking, config, db, docmatch, extract, providers, rerank as reranker
from .models import Chunk, Document
from .storage import document_prefix, get_storage

log = logging.getLogger("docqa")


def ingest(document_id: int) -> None:
    """Background job: read the stored PDF, chunk it, embed the chunks, save them."""
    with db.session() as s:
        doc = s.get(Document, document_id)
        if doc is None:
            return
        try:
            pdf = extract.extract_pdf(get_storage().get(doc.storage_key))
            size = doc.chunk_words or config.CHUNK_WORDS
            overlap = doc.chunk_overlap if doc.chunk_overlap is not None else config.CHUNK_OVERLAP_WORDS
            pieces = chunking.chunk_pages(pdf.pages, size, overlap)
            title = pdf.title or doc.filename.removesuffix(".pdf").removesuffix(".PDF")
            where = [chunking.page_label(pdf.sections[p], pdf.headings[p]) for p in range(len(pdf.pages))]
            vectors = providers.embed([chunking.with_context(title, where[page - 1], text)
                                       for page, text in pieces], query=False)
            s.add_all(Chunk(document_id=doc.id, user_id=doc.user_id, page=page, position=i, text=text, embedding=vec,
                            section=where[page - 1])
                      for i, ((page, text), vec) in enumerate(zip(pieces, vectors)))
            doc.page_count, doc.chunk_count, doc.status, doc.error = len(pdf.pages), len(pieces), "ready", None
            doc.embedding_model = config.current_embedding_model()
            doc.pdf_title, doc.pdf_author, doc.pdf_created = pdf.title, pdf.author, pdf.created
        except (extract.ExtractError, providers.ProviderError) as e:
            s.rollback()
            doc.status, doc.error = "failed", str(e)
        except Exception:
            log.exception("ingest failed for document %s", document_id)
            s.rollback()
            doc.status, doc.error = "failed", "Something went wrong while processing this file."
        try:
            s.commit()   # the chunk inserts are flushed here, so this is where a bad vector or text can fail
        except Exception:
            log.exception("saving document %s failed", document_id)
            s.rollback()
            doc = s.get(Document, document_id)   # gone if it was deleted meanwhile
            if doc is not None:
                doc.status, doc.error = "failed", "Something went wrong while saving this file."
                s.commit()


@dataclass
class Hit:
    chunk_id: int
    document_id: int
    filename: str
    page: int
    text: str
    section: str | None
    title: str | None
    score: float                      # cosine similarity, higher is better
    rank: int = 0                     # position in the list before reranking (vector and keyword results merged)
    vector_rank: int | None = None    # 1 = closest by vector similarity; None = not in the vector results
    keyword_rank: int | None = None   # 1 = best BM25 match; None = not in the keyword results
    keyword_score: float | None = None
    rerank_score: float | None = None
    rerank_rank: int | None = None    # 1 = best after reranking


RRF_K = 60   # reciprocal rank fusion: each list gives 1 / (RRF_K + rank), and the lists are added


def _eligible(user_id: int, document_ids: list[int] | None):
    """Chunks this user may be searched: ready documents made with the current embedding model."""
    where = [Chunk.user_id == user_id, Document.status == "ready",
             Document.embedding_model == config.current_embedding_model()]  # other models' vectors can't be compared
    if document_ids:
        where.append(Chunk.document_id.in_(document_ids))
    return where


def _title(pdf_title: str | None, filename: str) -> str:
    return pdf_title or filename.removesuffix(".pdf").removesuffix(".PDF")


def retrieve(s: Session, user_id: int, question: str, document_ids: list[int] | None,
             candidates: int, hybrid: bool = True, *, bm25_header: bool = True, name_boost: bool = True) -> list[Hit]:
    """The `candidates` best chunks of this user's ready documents, best first. Vector search finds chunks that
    mean the same as the question; with `hybrid`, a BM25 keyword search adds chunks that contain its exact terms,
    and the rankings are merged. `bm25_header` lets the keyword search also see each chunk's title and section.
    `name_boost` also searches inside the documents whose title the question mentions (several documents only)."""
    (qvec,) = providers.embed([question], query=True)
    distance = Chunk.embedding.cosine_distance(qvec)
    where = _eligible(user_id, document_ids)
    by_id: dict[int, Hit] = {}

    def vector_list(extra_where, limit: int) -> list[int]:
        stmt = (select(Chunk, Document.filename, Document.pdf_title, distance.label("d"))
                .join(Document, Document.id == Chunk.document_id).where(*where, *extra_where)
                .order_by(distance).limit(limit))
        order = []
        for c, name, pdf_title, d in s.execute(stmt):
            by_id.setdefault(c.id, Hit(c.id, c.document_id, name, c.page, c.text, c.section, _title(pdf_title, name),
                                       round(1 - d, 4)))
            order.append(c.id)
        return order

    def keyword_list(extra_where, limit: int) -> list[tuple[int, float]]:
        rows = s.execute(select(Chunk.id, Chunk.text, Chunk.section, Document.pdf_title, Document.filename)
                         .join(Document, Document.id == Chunk.document_id).where(*where, *extra_where)).all()
        texts = [(cid, chunking.with_context(_title(t, f), sec, text) if bm25_header else text)
                 for cid, text, sec, t, f in rows]
        return bm25.rank(question, texts, limit)

    vector_order = vector_list([], candidates)
    for i, cid in enumerate(vector_order, start=1):
        by_id[cid].vector_rank = i
    keyword_ranked = keyword_list([], candidates) if hybrid else []
    lists = [vector_order, [cid for cid, _ in keyword_ranked]]

    if name_boost:
        docs = s.execute(select(Document.id, Document.pdf_title, Document.filename).join(Chunk, Chunk.document_id == Document.id)
                         .where(*where).distinct()).all()
        named = docmatch.named_documents(question, [(i, f"{t or ''} {f}") for i, t, f in docs])   # title and file name: titles are often just filing numbers
        if named and len(named) < len(docs):   # the question names some, not all, of the documents searched
            inside = [Chunk.document_id.in_(named)]
            lists.append(vector_list(inside, candidates))
            if hybrid:
                lists.append([cid for cid, _ in keyword_list(inside, candidates)])

    missing = list(dict.fromkeys(cid for order in lists for cid in order if cid not in by_id))
    if missing:   # found by keywords only, or only inside a named document: fetch their similarity in one query
        stmt = (select(Chunk, Document.filename, Document.pdf_title, distance.label("d"))
                .join(Document, Document.id == Chunk.document_id).where(Chunk.id.in_(missing)))
        for c, name, pdf_title, d in s.execute(stmt):
            by_id[c.id] = Hit(c.id, c.document_id, name, c.page, c.text, c.section, _title(pdf_title, name), round(1 - d, 4))
    for i, (cid, score) in enumerate(keyword_ranked, start=1):
        by_id[cid].keyword_rank, by_id[cid].keyword_score = i, round(score, 3)

    fused = {cid: 0.0 for cid in by_id}
    for order in lists:
        for i, cid in enumerate(order, start=1):
            fused[cid] += 1 / (RRF_K + i)
    ordered = sorted(by_id.values(), key=lambda h: (-fused[h.chunk_id], h.vector_rank or 10**9))[:candidates]
    for i, h in enumerate(ordered, start=1):
        h.rank = i
    return ordered


def rerank(question: str, hits: list[Hit]) -> list[Hit]:
    """Score every candidate against the question and return them best first (ranks are filled in)."""
    scores = reranker.rerank(question, [chunking.with_context(h.title, h.section, h.text) for h in hits])
    for h, score in zip(hits, scores):
        h.rerank_score = round(score, 4)
    ordered = sorted(hits, key=lambda h: -h.rerank_score)
    for i, h in enumerate(ordered, start=1):
        h.rerank_rank = i
    return ordered


SYSTEM = (
    "You answer questions using only the numbered passages provided. "
    "Cite the passages you used like [1] or [2][3]. "
    "If the passages do not contain the answer, say you could not find it in the documents. "
    "Do not use outside knowledge."
)


def answer(question: str, hits: list[Hit], model: str | None = None) -> str:
    if not hits:
        return "I could not find anything in the documents."
    passages = "\n\n".join(f"[{i}] ({h.filename}, page {h.page})\n{h.text}" for i, h in enumerate(hits, start=1))
    return providers.generate(SYSTEM, f"Passages:\n\n{passages}\n\nQuestion: {question}", model)


def delete_document_files(user_id: int, document_id: int) -> None:
    get_storage().delete_prefix(document_prefix(user_id, document_id))
