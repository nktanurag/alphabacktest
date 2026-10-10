import numpy as np
import pandas as pd
import pytest

from alphabacktest.engine import run_backtest
from alphabacktest.indicators import ema, rsi, sma
from alphabacktest.models import Strategy


def bars(closes):
    dates = pd.date_range("2024-01-01", periods=len(closes)).strftime("%Y-%m-%d")
    c = np.array(closes, float)
    return pd.DataFrame({"date": dates, "open": c, "high": c, "low": c, "close": c, "volume": 1000.0})


def cond(id_, name, op, value, period=None):
    return {"id": id_, "left": {"name": name, **({"period": period} if period else {})},
            "operator": op, "right": {"kind": "value", "value": value}}


def strat(conds, **kw):
    base = dict(name="t", asset="X", startDate="2024-01-01", endDate="2024-12-31", entryConditions=conds,
                exitDays=2, initialCapital=1000, positionSizePct=100, commissionPct=0, slippagePct=0)
    return Strategy(**{**base, **kw})


def test_sma():
    assert sma(pd.Series([1, 2, 3, 4.0]), 2).tolist()[1:] == [1.5, 2.5, 3.5]


def test_ema_seeded_with_sma():
    out = ema(pd.Series([1, 2, 3, 4, 5.0]), 3)
    assert out.iloc[2] == 2.0 and out.iloc[3] == pytest.approx(3.0)


def test_rsi_100_on_monotonic_rise():
    assert rsi(pd.Series([1, 2, 3, 4, 5.0]), 3).iloc[-1] == 100


def test_and_logic_next_open_entry_and_fixed_exit():
    r = run_backtest(strat([cond("1", "PRICE", "crosses_above", 5), cond("2", "VOLUME", "greater_than", 500)]),
                     bars([4, 4, 4, 6, 7, 8, 9, 9]))
    assert r.totalTrades == 1
    t = r.trades[0]
    assert (t.entryPrice, t.exitPrice, t.holdingDays) == (7, 9, 2)
    assert t.returnPct == pytest.approx(28.57, abs=0.01)
    assert len(t.entryReasons) == 2
    assert r.totalReturnPct == pytest.approx(28.57, abs=0.01)


def test_costs_reduce_return():
    r = run_backtest(strat([cond("1", "PRICE", "greater_than", 5)], commissionPct=1, slippagePct=1),
                     bars([4, 6, 6, 6, 6, 6]))
    assert r.trades[0].returnPct < 0


def test_no_trades():
    r = run_backtest(strat([cond("1", "PRICE", "greater_than", 99)]), bars([1, 2, 3, 4]))
    assert r.totalTrades == 0


def test_empty_strategy_rejected():
    with pytest.raises(ValueError, match="entry condition"):
        run_backtest(strat([]), bars([1, 2, 3]))


def test_signal_close_fills_at_signal_bar_close():
    r = run_backtest(strat([cond("1", "PRICE", "crosses_above", 5)], entryTiming="signal_close"),
                     bars([4, 4, 4, 6, 7, 8, 9, 9]))
    t = r.trades[0]
    assert (t.entryDate, t.entryPrice, t.exitPrice, t.holdingDays) == ("2024-01-04", 6, 8, 2)
    assert t.returnPct == pytest.approx(33.33, abs=0.01)


def test_open_trade_closed_at_end_of_range_and_data_after_is_ignored():
    # signal at idx 2, entry idx 3 (open 7); range ends at idx 4 although exitDays=5.
    data = bars([4, 4, 6, 7, 8, 100, 100, 100])
    r = run_backtest(strat([cond("1", "PRICE", "crosses_above", 5)], exitDays=5, endDate="2024-01-05"), data)
    t = r.trades[0]
    assert (t.exitDate, t.exitPrice, t.holdingDays, t.exitReason) == ("2024-01-05", 8, 1, "Backtest period ended")
    assert any("closed early" in w for w in r.warnings)
    # metrics agree with the trade list
    assert r.totalReturnPct == pytest.approx(t.returnPct, abs=0.01)


def test_currency_defaults_to_usd_and_follows_data():
    d = bars([4, 6, 6, 6, 6, 6])
    assert run_backtest(strat([cond("1", "PRICE", "greater_than", 99)]), d).currency == "USD"
    d.attrs["currency"] = "INR"
    assert run_backtest(strat([cond("1", "PRICE", "greater_than", 99)]), d).currency == "INR"


# ── exit rules ────────────────────────────────────────────────────────────────

def ohlc(rows):
    """rows: (open, high, low, close)."""
    dates = pd.date_range("2024-01-01", periods=len(rows)).strftime("%Y-%m-%d")
    o, h, l, c = (np.array(x, float) for x in zip(*rows))
    return pd.DataFrame({"date": dates, "open": o, "high": h, "low": l, "close": c, "volume": 1000.0})


ENTER_ON_6 = cond("1", "PRICE", "crosses_above", 5)


def test_stop_loss_fills_at_level_intrabar():
    # signal on bar2 (close 6); enter bar3 open 10; bar4 low 8.9 breaches 10% stop (9.0) -> fill at 9.0
    d = ohlc([(4, 4, 4, 4), (4, 4, 4, 4), (6, 6, 6, 6), (10, 10, 9.5, 9.8), (9.6, 9.7, 8.9, 9.0), (9, 9, 9, 9), (9, 9, 9, 9)])
    r = run_backtest(strat([ENTER_ON_6], exitDays=None, stopLossPct=10), d)
    t = r.trades[0]
    assert (t.entryPrice, t.exitPrice, t.exitDate) == (10, 9.0, "2024-01-05")
    assert t.exitReason.startswith("Stop-loss")


def test_stop_loss_gap_fills_at_open():
    d = ohlc([(4, 4, 4, 4), (4, 4, 4, 4), (6, 6, 6, 6), (10, 10, 10, 10), (7, 7.5, 6.5, 7), (7, 7, 7, 7), (7, 7, 7, 7)])
    r = run_backtest(strat([ENTER_ON_6], exitDays=None, stopLossPct=10), d)
    assert r.trades[0].exitPrice == 7  # gapped below the 9.0 stop: fill at the open, not the stop


def test_take_profit():
    d = ohlc([(4, 4, 4, 4), (4, 4, 4, 4), (6, 6, 6, 6), (10, 10, 10, 10), (10, 11.5, 10, 11), (11, 11, 11, 11), (11, 11, 11, 11)])
    r = run_backtest(strat([ENTER_ON_6], exitDays=None, takeProfitPct=10), d)
    t = r.trades[0]
    assert t.exitPrice == pytest.approx(11.0) and t.exitReason.startswith("Take-profit")


def test_stop_wins_when_bar_hits_both():
    d = ohlc([(4, 4, 4, 4), (4, 4, 4, 4), (6, 6, 6, 6), (10, 10, 10, 10), (10, 12, 8, 10), (10, 10, 10, 10), (10, 10, 10, 10)])
    r = run_backtest(strat([ENTER_ON_6], exitDays=None, stopLossPct=10, takeProfitPct=10), d)
    assert r.trades[0].exitReason.startswith("Stop-loss")


def test_signal_exit_next_open_vs_signal_close():
    d = bars([4, 4, 6, 7, 8, 9, 20, 21, 21, 21])
    exit_when_over_15 = cond("x", "PRICE", "greater_than", 15)
    nxt = run_backtest(strat([ENTER_ON_6], exitDays=None, exitConditions=[exit_when_over_15]), d).trades[0]
    same = run_backtest(strat([ENTER_ON_6], exitDays=None, exitConditions=[exit_when_over_15], entryTiming="signal_close"), d).trades[0]
    assert (nxt.exitDate, nxt.exitPrice) == ("2024-01-08", 21)   # signal on 01-07 close, fill next open
    assert (same.exitDate, same.exitPrice) == ("2024-01-07", 20)  # fill at the signal bar's close
    assert nxt.exitReason.startswith("Exit signal")


def test_time_exit_still_works_alongside_other_rules():
    r = run_backtest(strat([ENTER_ON_6], exitDays=2, stopLossPct=50), bars([4, 4, 6, 7, 8, 9, 9, 9]))
    assert r.trades[0].exitReason == "2 trading days reached"


def test_requires_at_least_one_exit_rule():
    with pytest.raises(ValueError, match="exit rule"):
        run_backtest(strat([ENTER_ON_6], exitDays=None), bars([4, 6, 7]))


def test_buy_and_hold_benchmark_and_curves():
    r = run_backtest(strat([cond("1", "PRICE", "greater_than", 99)]), bars([10, 11, 12, 9, 15]))
    assert r.buyHoldReturnPct == 50.0
    assert r.buyHoldMaxDrawdownPct == pytest.approx(-25.0)  # 12 -> 9
    assert len(r.equityCurve) == len(r.benchmarkCurve) == 5
    assert r.equityCurve[-1].value == 1000  # never traded
    assert r.benchmarkCurve[-1].value == 1500
