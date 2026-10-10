import time
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_TTL = 6 * 3600
# Calendar days of history fetched before startDate so long indicators (e.g. SMA 200) are warm.
WARMUP_DAYS = 400


def fetch_daily_bars(symbol: str, start: str, end: str) -> pd.DataFrame:
    key = f"{symbol.upper()}|{start}|{end}"
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]

    p1 = date.fromisoformat(start) - timedelta(days=WARMUP_DAYS)
    # yfinance's end is exclusive; the engine never looks past endDate.
    p2 = date.fromisoformat(end) + timedelta(days=1)
    ticker = yf.Ticker(symbol.upper())
    raw = ticker.history(start=p1.isoformat(), end=p2.isoformat(), interval="1d", auto_adjust=True)
    if raw.empty:
        raise LookupError(f"No data for {symbol}")
    df = pd.DataFrame({
        "date": raw.index.strftime("%Y-%m-%d"),
        "open": raw["Open"].to_numpy(), "high": raw["High"].to_numpy(),
        "low": raw["Low"].to_numpy(), "close": raw["Close"].to_numpy(),
        "volume": raw["Volume"].to_numpy(),
    }).dropna()
    try:
        df.attrs["currency"] = ticker.history_metadata.get("currency") or "USD"
    except Exception:
        df.attrs["currency"] = "USD"
    _CACHE[key] = (time.time(), df)
    return df


_SEARCH_CACHE: dict[str, tuple[float, list[dict]]] = {}


def search_symbols(query: str, limit: int = 8) -> list[dict]:
    """Search tradable stocks/ETFs by ticker or company name."""
    q = query.strip()
    if not q:
        return []
    key = q.lower()
    hit = _SEARCH_CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    quotes = yf.Search(q, max_results=limit * 2, news_count=0).quotes
    out = [
        {"symbol": x["symbol"], "name": x.get("longname") or x.get("shortname") or x["symbol"],
         "exchange": x.get("exchDisp") or "", "type": x["quoteType"]}
        for x in quotes if x.get("quoteType") in ("EQUITY", "ETF") and x.get("symbol")
    ][:limit]
    _SEARCH_CACHE[key] = (time.time(), out)
    return out
