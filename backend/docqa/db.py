from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


_engine = None
_sessions = None


def _normalize(url: str) -> str:
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def engine():
    global _engine, _sessions
    if _engine is None:
        url = config.database_url()
        if url is None:
            raise RuntimeError("DOCQA_DATABASE_URL is not set")
        _engine = create_engine(_normalize(url))
        _sessions = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset() -> None:
    """Forget the engine (tests point DOCQA_DATABASE_URL somewhere else)."""
    global _engine, _sessions
    if _engine is not None:
        _engine.dispose()
    _engine = _sessions = None


def session() -> Session:
    engine()
    return _sessions()


def get_db() -> Iterator[Session]:
    with session() as s:
        yield s


_ADDED_COLUMNS = [
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_hash VARCHAR(64)",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(200)",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS chunk_words INTEGER",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS chunk_overlap INTEGER",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS pdf_title VARCHAR(500)",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS pdf_author VARCHAR(500)",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS pdf_created VARCHAR(50)",
    "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS section VARCHAR(500)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_user_hash ON documents (user_id, file_hash)",
]


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)
    with engine().begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine())
    # create_all never alters existing tables, so add columns introduced later.
    with engine().begin() as conn:
        for stmt in _ADDED_COLUMNS:
            conn.execute(text(stmt))
