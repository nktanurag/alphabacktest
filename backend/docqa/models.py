from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import EMBED_DIM
from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("user_id", "file_hash", name="uq_documents_user_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # The id of the signed-in user in the main app. No foreign key: separate system.
    user_id: Mapped[int] = mapped_column(index=True)
    filename: Mapped[str] = mapped_column(String(300))
    file_type: Mapped[str] = mapped_column(String(20))
    size_bytes: Mapped[int]
    page_count: Mapped[int] = mapped_column(default=0)
    chunk_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), default="processing")  # processing | ready | failed
    error: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(String(500), default="")
    file_hash: Mapped[str | None] = mapped_column(String(64))            # sha256 of the file; stops duplicate uploads
    embedding_model: Mapped[str | None] = mapped_column(String(200))     # model that made this document's vectors
    chunk_words: Mapped[int | None]
    chunk_overlap: Mapped[int | None]
    pdf_title: Mapped[str | None] = mapped_column(String(500))           # from the PDF's own metadata
    pdf_author: Mapped[str | None] = mapped_column(String(500))
    pdf_created: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan",
                                                 passive_deletes=True)   # the database cascades; do not load every vector first


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(index=True)   # repeated here so every search filters by owner
    page: Mapped[int]
    position: Mapped[int]                                # order within the document
    section: Mapped[str | None] = mapped_column(String(500))   # heading path from the PDF's bookmarks, if it has any
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))

    document: Mapped[Document] = relationship(back_populates="chunks")
