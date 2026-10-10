import numpy as np
import pandas as pd

from .models import Indicator


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    """EMA seeded with the SMA of the first n valid values (standard convention)."""
    out = np.full(len(s), np.nan)
    valid = np.flatnonzero(~np.isnan(s.to_numpy(dtype=float)))
    if len(valid) < n:
        return pd.Series(out, index=s.index)
    k = 2 / (n + 1)
    v = s.to_numpy(dtype=float)
    seed = valid[n - 1]
    out[seed] = v[valid[:n]].mean()
    for i in range(seed + 1, len(v)):
        out[i] = v[i] * k + out[i - 1] * (1 - k)
    return pd.Series(out, index=s.index)


def rsi(s: pd.Series, n: int) -> pd.Series:
    """Wilder's RSI."""
    v = s.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    if len(v) <= n:
        return pd.Series(out, index=s.index)
    d = np.diff(v)
    gain = np.maximum(d, 0.0)
    loss = np.maximum(-d, 0.0)
    ag, al = gain[:n].mean(), loss[:n].mean()
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(v)):
        ag = (ag * (n - 1) + gain[i - 1]) / n
        al = (al * (n - 1) + loss[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return pd.Series(out, index=s.index)


def bollinger(s: pd.Series, n: int, side: int) -> pd.Series:
    """Bollinger band with 2 population standard deviations."""
    return sma(s, n) + side * 2 * s.rolling(n).std(ddof=0)


def macd(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    line = ema(s, 12) - ema(s, 26)
    return line, ema(line, 9)


NEEDS_PERIOD = {"SMA", "EMA", "RSI", "BB_UPPER", "BB_LOWER"}


def compute_series(op: Indicator, df: pd.DataFrame) -> pd.Series:
    close = df["close"]
    n = op.period or 0
    if op.name in NEEDS_PERIOD and n < 1:
        raise ValueError(f"{op.name} requires a period of at least 1")
    match op.name:
        case "PRICE":
            return close
        case "VOLUME":
            # With a period, "Volume(20)" means the 20-bar average volume.
            return sma(df["volume"], n) if n else df["volume"]
        case "SMA":
            return sma(close, n)
        case "EMA":
            return ema(close, n)
        case "RSI":
            return rsi(close, n)
        case "BB_UPPER":
            return bollinger(close, n, 1)
        case "BB_LOWER":
            return bollinger(close, n, -1)
        case "MACD":
            return macd(close)[0]
        case "MACD_SIGNAL":
            return macd(close)[1]
    raise ValueError(f"Unknown indicator {op.name}")
