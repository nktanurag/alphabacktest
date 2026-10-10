"""Cross-check our indicators against the `ta` library on a deterministic random walk.

Conventions differ in the first bars only (we seed EMA/RSI with an SMA, `ta` seeds with the
first value), and that difference decays geometrically, so compare after a long warm-up.
"""
import numpy as np
import pandas as pd
import pytest
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, SMAIndicator
from ta.volatility import BollingerBands

from alphabacktest.indicators import bollinger, ema, macd, rsi, sma

rng = np.random.default_rng(42)
CLOSE = pd.Series(100 + np.cumsum(rng.normal(0, 1.5, 600)))
TAIL = slice(-200, None)


def close(ours, theirs):
    np.testing.assert_allclose(ours.to_numpy()[TAIL], theirs.to_numpy()[TAIL], rtol=1e-6)


@pytest.mark.parametrize("n", [5, 20, 50])
def test_sma(n):
    close(sma(CLOSE, n), SMAIndicator(CLOSE, n).sma_indicator())


@pytest.mark.parametrize("n", [5, 20, 50])
def test_ema(n):
    close(ema(CLOSE, n), EMAIndicator(CLOSE, n).ema_indicator())


@pytest.mark.parametrize("n", [7, 14, 30])
def test_rsi(n):
    close(rsi(CLOSE, n), RSIIndicator(CLOSE, n).rsi())


@pytest.mark.parametrize("n", [10, 20])
def test_bollinger(n):
    bb = BollingerBands(CLOSE, n, 2)
    close(bollinger(CLOSE, n, 1), bb.bollinger_hband())
    close(bollinger(CLOSE, n, -1), bb.bollinger_lband())


def test_macd():
    ref = MACD(CLOSE, 26, 12, 9)
    line, signal = macd(CLOSE)
    close(line, ref.macd())
    close(signal, ref.macd_signal())
