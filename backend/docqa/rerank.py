"""Reranking with a small cross-encoder that runs on this machine (fastembed, ONNX; no API key).

A cross-encoder reads the question and a passage together, so it orders passages better than
comparing precomputed vectors. The model (about 150 MB) downloads on first use.
"""
import logging
import threading

from . import config
from .providers import ProviderError

log = logging.getLogger("docqa")

_model = None
_lock = threading.Lock()


def _load():
    global _model
    with _lock:
        if _model is None:
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder
                _model = TextCrossEncoder(config.rerank_model(), cache_dir=str(config.model_cache_dir()))
            except Exception as e:
                log.exception("reranker could not be loaded")
                raise ProviderError(f"The reranking model could not be loaded. Check the server log ({type(e).__name__}).")
        return _model


def rerank(query: str, texts: list[str]) -> list[float]:
    """One relevance score per text (higher is better), in the same order as `texts`."""
    if not texts:
        return []
    return [float(s) for s in _load().rerank(query, texts)]
