"""Keyword ranking (BM25) over a user's chunks, to catch exact terms that vector search blurs away."""
import math
import re
from collections import Counter

K1, B = 1.5, 0.75
_WORD = re.compile(r"\w+")
# Question words and glue words carry no signal; keeping them would let "what does the" match everything.
_STOP = frozenset("""a an and are as at be been by can could did do does for from had has have how in into is it its of on or
that the their there these this those to was were what when where which who whom why will with would about than then
if not no so such""".split())

_cache: dict[tuple[int, int], tuple[Counter, int]] = {}   # (chunk id, hash of text) -> (term counts, length); the text is in the key so a reused id can never serve stale counts
_CACHE_MAX = 60_000


def tokenize(text: str) -> list[str]:
    out = []
    for w in _WORD.findall(text.lower()):
        if w in _STOP:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]   # crude plural folding: "plants" matches "plant"
        out.append(w)
    return out


def _counts(chunk_id: int, text: str) -> tuple[Counter, int]:
    key = (chunk_id, hash(text))
    hit = _cache.get(key)
    if hit is None:
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        toks = tokenize(text)
        hit = _cache[key] = (Counter(toks), len(toks))
    return hit


def rank(query: str, chunks: list[tuple[int, str]], limit: int) -> list[tuple[int, float]]:
    """The `limit` best (chunk_id, score) pairs for the query, best first; chunks sharing no term are left out.
    Rare terms count for more than common ones (that is what makes "CBG" beat "production")."""
    terms = set(tokenize(query))
    if not terms or not chunks:
        return []
    stats = [(cid, *_counts(cid, text)) for cid, text in chunks]
    n = len(stats)
    avg = (sum(length for _, _, length in stats) / n) or 1.0
    df = {t: sum(1 for _, tf, _ in stats if t in tf) for t in terms}
    idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items() if d}
    scored = []
    for cid, tf, length in stats:
        s = 0.0
        for t, w in idf.items():
            f = tf.get(t, 0)
            if f:
                s += w * f * (K1 + 1) / (f + K1 * (1 - B + B * length / avg))
        if s > 0:
            scored.append((cid, s))
    scored.sort(key=lambda x: -x[1])
    return scored[:limit]
