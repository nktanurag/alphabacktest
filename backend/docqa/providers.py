"""Embedding and answer-generation calls. Gemini's free tier today; the rest of the code only
uses `embed` and `generate`, so another provider is a change in this file."""
import logging
import re
import threading
import time

import requests

from . import config

_BASE = "https://generativelanguage.googleapis.com/v1beta"
_BATCH = 100
_BATCH_TOKENS = 12_000   # keep each call well under the free tier's tokens-per-minute limit
log = logging.getLogger("docqa")


class ProviderError(Exception):
    """A model call failed; the message is safe to show the user."""


def _retry_delay(body: str) -> float | None:
    """Seconds Google asks us to wait, from e.g. "retryDelay": "34s"."""
    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', body)
    return float(m.group(1)) if m else None


def _post(path: str, body: dict) -> dict:
    key = config.gemini_api_key()
    if not key:
        raise ProviderError("GEMINI_API_KEY is not set on the server.")
    for attempt in range(5):
        try:
            res = requests.post(f"{_BASE}/{path}", json=body, headers={"x-goog-api-key": key}, timeout=60)
        except requests.RequestException as e:
            log.warning("Gemini request failed: %s: %s", type(e).__name__, e)
            raise ProviderError("Could not reach the model service.")
        if res.status_code == 429:
            log.warning("Gemini 429: %s", res.text[:600])
            if "PerDay" in res.text:
                raise ProviderError("The free daily quota for this model is used up. It resets daily; try again tomorrow.")
            if attempt < 4:
                time.sleep(min(_retry_delay(res.text) or 2 ** (attempt + 2), 65) + 1)
                continue
            raise ProviderError("The free model quota is used up for now. Try again in a minute.")
        if res.status_code in (400, 403) and "API key" in res.text:
            raise ProviderError("The Gemini API key was rejected.")
        if res.status_code in (500, 502, 503, 504):   # "high demand" and similar: usually gone in seconds
            log.warning("Gemini %s (attempt %s): %s", res.status_code, attempt + 1, res.text[:300])
            if attempt < 4:
                time.sleep(3 * 2 ** attempt)   # 3, 6, 12, 24 seconds
                continue
            raise ProviderError("The model service is busy right now. Try again in a minute.")
        if not res.ok:
            log.warning("Gemini %s: %s", res.status_code, res.text[:600])
            raise ProviderError(f"The model service returned an error ({res.status_code}).")
        return res.json()
    raise ProviderError("The model service is busy.")


def _batches(texts: list[str]):
    """Groups of texts, each within the call size and a rough token budget (about 1.4 tokens per word)."""
    batch, tokens = [], 0
    for t in texts:
        cost = int(len(t.split()) * 1.4) + 1
        if batch and (len(batch) >= _BATCH or tokens + cost > _BATCH_TOKENS):
            yield batch
            batch, tokens = [], 0
        batch.append(t)
        tokens += cost
    if batch:
        yield batch


_local = None
_local_lock = threading.Lock()


def _local_model():
    """The local embedding model, created once. The lock covers only the creation (a download and load that can take
    a minute), so embedding a question never waits behind a long ingest."""
    global _local
    with _local_lock:
        if _local is None:
            try:
                from fastembed import TextEmbedding
                _local = TextEmbedding(config.local_embedding_model(), cache_dir=str(config.model_cache_dir()))
            except Exception as e:
                log.exception("local embedding model could not be loaded")
                raise ProviderError("The local embedding model could not be loaded. Check the server log and the "
                                    f"model cache folder ({type(e).__name__}).")
        return _local


def _embed_local(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _local_model().embed(texts, batch_size=8)]


def embed(texts: list[str], *, query: bool) -> list[list[float]]:
    """One vector (config.EMBED_DIM numbers) per text. Local model by default; Gemini if configured."""
    if config.embedding_provider() == "gemini":
        return _embed_gemini(texts, query=query)
    return _embed_local(texts)


def _embed_gemini(texts: list[str], *, query: bool) -> list[list[float]]:
    model = config.embedding_model()
    task = "RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT"
    vectors: list[list[float]] = []
    for batch in _batches(texts):
        body = {"requests": [{
            "model": f"models/{model}",
            "content": {"parts": [{"text": t}]},
            "taskType": task,
            "outputDimensionality": config.EMBED_DIM,
        } for t in batch]}
        data = _post(f"models/{model}:batchEmbedContents", body)
        vectors.extend(e["values"] for e in data["embeddings"])
    return vectors


_NOT_FOR_ANSWERS = ("image", "tts", "audio", "embedding", "live", "robotics", "computer-use", "imagen", "veo", "aqa")
_models_cache: tuple[float, list[dict]] | None = None
_MODELS_TTL = 600.0


def list_generation_models() -> list[dict]:
    """Models this key can use to write answers: [{"id": "gemini-...", "name": "display name"}], cached for 10 minutes.
    Asks Google's model list and keeps those that support generateContent, minus image, audio, TTS and similar."""
    global _models_cache
    if _models_cache and time.time() - _models_cache[0] < _MODELS_TTL:
        return _models_cache[1]
    key = config.gemini_api_key()
    if not key:
        raise ProviderError("GEMINI_API_KEY is not set on the server.")
    found, token = [], None
    for _ in range(10):   # follow pages, with a hard stop
        try:
            res = requests.get(f"{_BASE}/models", params={"pageSize": 1000, **({"pageToken": token} if token else {})},
                               headers={"x-goog-api-key": key}, timeout=20)
        except requests.RequestException as e:
            log.warning("Gemini model list failed: %s: %s", type(e).__name__, e)
            raise ProviderError("Could not reach the model service.")
        if res.status_code in (400, 403) and "API key" in res.text:
            raise ProviderError("The Gemini API key was rejected.")
        if not res.ok:
            log.warning("Gemini model list %s: %s", res.status_code, res.text[:300])
            raise ProviderError(f"The model service returned an error ({res.status_code}).")
        data = res.json()
        for m in data.get("models", []):
            mid = m.get("name", "").removeprefix("models/")
            if ("generateContent" in m.get("supportedGenerationMethods", []) and mid.startswith("gemini")
                    and not any(w in mid for w in _NOT_FOR_ANSWERS)):
                found.append({"id": mid, "name": m.get("displayName") or mid})
        token = data.get("nextPageToken")
        if not token:
            break
    found.sort(key=lambda m: m["id"])
    _models_cache = (time.time(), found)
    return found


def generate(system: str, prompt: str, model: str | None = None) -> str:
    data = _post(f"models/{model or config.generation_model()}:generateContent", {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
    })
    try:
        return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]).strip()
    except (KeyError, IndexError):
        raise ProviderError("The model returned no answer.")
