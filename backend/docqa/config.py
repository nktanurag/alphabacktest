import os
from pathlib import Path

EMBED_DIM = 768

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PAGES = 600
MAX_DOCS_PER_USER = 20

CHUNK_WORDS = 300             # defaults; each upload may choose its own
CHUNK_OVERLAP_WORDS = 50
MIN_CHUNK_WORDS = 100
MAX_CHUNK_WORDS = 800
DEFAULT_TOP_K = 5
MAX_TOP_K = 20


def database_url() -> str | None:
    return os.environ.get("DOCQA_DATABASE_URL") or None


def enabled() -> bool:
    return database_url() is not None


def storage_dir() -> Path:
    return Path(os.environ.get("DOCQA_STORAGE_DIR", "./docqa_files")).resolve()


def model_cache_dir() -> Path:
    """Where the local models are kept. fastembed's own default is the system temp folder, which the OS may clear."""
    raw = os.environ.get("DOCQA_MODEL_CACHE_DIR") or os.environ.get("FASTEMBED_CACHE_PATH") or "./.model_cache"
    return Path(raw).expanduser().resolve()


def gemini_api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or None


def embedding_model() -> str:
    return os.environ.get("DOCQA_EMBEDDING_MODEL", "gemini-embedding-001")


def generation_model() -> str:
    return os.environ.get("DOCQA_GENERATION_MODEL", "gemini-3.8-flash")


DEFAULT_CANDIDATES = 30
MAX_CANDIDATES = 100


def rerank_model() -> str:
    return os.environ.get("DOCQA_RERANK_MODEL", "jinaai/jina-reranker-v1-turbo-en")


def embedding_provider() -> str:
    """"local" (default, runs on this machine) or "gemini"."""
    return os.environ.get("DOCQA_EMBEDDING_PROVIDER", "local").lower()


def local_embedding_model() -> str:
    # 768 dimensions and an 8,000-token input, so 500-word chunks are embedded in full.
    return os.environ.get("DOCQA_LOCAL_EMBEDDING_MODEL", "jinaai/jina-embeddings-v2-base-en")


DEFAULT_MIN_RERANK_SCORE = -2.5   # chosen from a calibration run, see docs/DOCQA.md


def min_rerank_score() -> float | None:
    """Default relevance cutoff for reranked results. DOCQA_MIN_RERANK_SCORE overrides it; "off" disables it."""
    raw = (os.environ.get("DOCQA_MIN_RERANK_SCORE") or "").strip().lower()
    if raw in ("off", "none"):
        return None
    try:
        return float(raw) if raw else DEFAULT_MIN_RERANK_SCORE
    except ValueError:
        return DEFAULT_MIN_RERANK_SCORE


# How passages are cleaned and turned into text before embedding. Part of the stored model name, so changing it
# marks older documents stale.
EMBED_RECIPE = "title+section+clean+heading"


def current_embedding_model() -> str:
    """Name of the model that makes vectors right now; stored with each document."""
    model = embedding_model() if embedding_provider() == "gemini" else local_embedding_model()
    return f"{model} | {EMBED_RECIPE}"
