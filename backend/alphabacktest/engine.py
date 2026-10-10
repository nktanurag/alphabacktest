import math
from datetime import datetime

import numpy as np
import pandas as pd

from .indicators import NEEDS_PERIOD, compute_series
from .models import BacktestResult, Condition, EquityPoint, Operand, Strategy, Trade, Value

LABEL = {
    "SMA": "SMA", "EMA": "EMA", "RSI": "RSI", "BB_UPPER": "BB Upper", "BB_LOWER": "BB Lower",
    "MACD": "MACD", "MACD_SIGNAL": "MACD Signal", "VOLUME": "Volume", "PRICE": "Price",
}
# (past tense for trade explanations, symbol for summaries)
OP_TEXT = {
    "crosses_above": ("crossed above", "crosses above"),
    "crosses_below": ("crossed below", "crosses below"),
    "greater_than": ("was greater than", ">"),
    "less_than": ("was less than", "<"),
    "equals": ("equaled", "="),
}


def operand_label(op: Operand) -> str:
    if isinstance(op, Value):
        return f"{op.value:g}"
    return f"{LABEL[op.name]}({op.period})" if op.period else LABEL[op.name]


def condition_label(c: Condition) -> str:
    return f"{operand_label(c.left)} {OP_TEXT[c.operator][1]} {operand_label(c.right)}"


def _period_errors(label: str, conds: list[Condition]) -> list[str]:
    errs = []
    for i, c in enumerate(conds, 1):
        for o in (c.left, c.right):
            if not isinstance(o, Value) and o.name in NEEDS_PERIOD and not (o.period and o.period >= 1):
                errs.append(f"{label} {i}: period must be greater than 0.")
    return errs


def validate_strategy(s: Strategy) -> list[str]:
    errs: list[str] = []
    if not s.asset.strip():
        errs.append("Select an asset.")
    if not s.startDate < s.endDate:
        errs.append("Start date must be before end date.")
    if not s.entryConditions:
        errs.append("Add at least one entry condition.")
    if s.exitDays is not None and s.exitDays < 1:
        errs.append("Holding period must be at least 1 trading day.")
    if s.stopLossPct is not None and not 0 < s.stopLossPct < 100:
        errs.append("Stop-loss must be between 0 and 100%.")
    if s.takeProfitPct is not None and s.takeProfitPct <= 0:
        errs.append("Take-profit must be greater than 0%.")
    if s.exitDays is None and s.stopLossPct is None and s.takeProfitPct is None and not s.exitConditions:
        errs.append("Add at least one exit rule.")
    if s.initialCapital <= 0:
        errs.append("Initial capital must be greater than 0.")
    if not 0 < s.positionSizePct <= 100:
        errs.append("Position size must be between 0 and 100%.")
    if s.commissionPct < 0 or s.slippagePct < 0:
        errs.append("Commission and slippage cannot be negative.")
    errs += _period_errors("Condition", s.entryConditions)
    errs += _period_errors("Exit condition", s.exitConditions)
    return errs


def _series(op: Operand, df: pd.DataFrame) -> np.ndarray:
    if isinstance(op, Value):
        return np.full(len(df), op.value)
    return compute_series(op, df).to_numpy(dtype=float)


def _holds(op: str, l: np.ndarray, r: np.ndarray, i: int) -> bool:
    a, b = l[i], r[i]
    if math.isnan(a) or math.isnan(b):
        return False
    if op == "greater_than":
        return a > b
    if op == "less_than":
        return a < b
    if op == "equals":
        return abs(a - b) < 1e-9
    if i == 0 or math.isnan(l[i - 1]) or math.isnan(r[i - 1]):
        return False
    pa, pb = l[i - 1], r[i - 1]
    return (pa <= pb and a > b) if op == "crosses_above" else (pa >= pb and a < b)


def _r2(x: float) -> float:
    return round(float(x) + 0.0, 2)


def run_backtest(strategy: Strategy, df: pd.DataFrame) -> BacktestResult:
    """Long-only, one position at a time, all entry conditions ANDed.

    Fill timing (strategy.entryTiming) applies to entries and signal exits:
      next_open     act at the open of the bar after the signal bar (default, no look-ahead)
      signal_close  act at the signal bar's close

    Exit rules, first to trigger wins (checked in this order on each bar):
      1. a signal exit flagged on the previous bar (next_open mode) fills at this bar's open
      2. stop-loss, then take-profit, using the bar's low/high; a gap through the level fills
         at the open. If one bar could hit both, the stop-loss is assumed to hit first.
      3. fixed holding period: the close `exitDays` bars after entry
      4. last bar of the date range: closed at that close ("Backtest period ended")
      5. all exit conditions true at this bar's close
    `df` (columns date, open, high, low, close, volume; date as YYYY-MM-DD strings) may
    include history before startDate as indicator warm-up; signals are only taken inside
    [startDate, endDate].
    """
    errs = validate_strategy(strategy)
    if errs:
        raise ValueError(" ".join(errs))
    df = df.reset_index(drop=True)
    dates = df["date"].tolist()
    in_range = [strategy.startDate <= d <= strategy.endDate for d in dates]
    if not any(in_range):
        raise ValueError("No historical data in the selected period.")
    first_idx = in_range.index(True)
    last_idx = max(i for i, ok in enumerate(in_range) if ok)

    warnings: list[str] = []
    if dates[0] > strategy.startDate:
        warnings.append(f"Historical data starts on {dates[0]}, after the selected start date.")

    def prep(conds: list[Condition]):
        return [(c, _series(c.left, df), _series(c.right, df)) for c in conds]

    entry_conds, exit_conds = prep(strategy.entryConditions), prep(strategy.exitConditions)
    opens, highs, lows, closes = (df[c].to_numpy(float) for c in ("open", "high", "low", "close"))

    slip, fee, frac = strategy.slippagePct / 100, strategy.commissionPct / 100, strategy.positionSizePct / 100
    sl = strategy.stopLossPct / 100 if strategy.stopLossPct is not None else None
    tp = strategy.takeProfitPct / 100 if strategy.takeProfitPct is not None else None
    at_signal_close = strategy.entryTiming == "signal_close"
    cash = strategy.initialCapital
    trades: list[Trade] = []
    equity: list[tuple[str, float]] = []
    pos: dict | None = None

    def fill_entry(base_price: float) -> None:
        nonlocal cash
        price = base_price * (1 + slip)
        shares = cash * frac / (price * (1 + fee))
        cost = shares * price * (1 + fee)
        cash -= cost
        pos.update(shares=shares, price=price, cost=cost, filled=True)  # type: ignore[union-attr]

    def close_trade(i: int, base_price: float, reason: str) -> None:
        nonlocal cash, pos
        exit_price = base_price * (1 - slip)
        proceeds = pos["shares"] * exit_price * (1 - fee)
        pnl = proceeds - pos["cost"]
        cash += proceeds
        trades.append(Trade(
            id=len(trades) + 1, entryDate=dates[pos["entry_idx"]], entryPrice=_r2(pos["price"]),
            exitDate=dates[i], exitPrice=_r2(exit_price), holdingDays=i - pos["entry_idx"],
            returnPct=_r2(pnl / pos["cost"] * 100), pnl=_r2(pnl), result="WIN" if pnl > 0 else "LOSS",
            entryReasons=pos["reasons"], exitReason=reason,
        ))
        pos = None

    signal_exit_text = "Exit signal: " + " AND ".join(condition_label(c) for c, _, _ in exit_conds)

    for i in range(last_idx + 1):
        exited_now = False

        if pos and not at_signal_close and i == pos["entry_idx"]:
            fill_entry(opens[i])

        if pos and pos["filled"]:
            decision: tuple[float, str] | None = None
            if pos["exit_signal"] and i > pos["entry_idx"]:
                decision = (opens[i], signal_exit_text)
            if decision is None and sl is not None:
                level = pos["price"] * (1 - sl)
                if opens[i] <= level:
                    decision = (opens[i], f"Stop-loss hit ({strategy.stopLossPct:g}% below entry)")
                elif lows[i] <= level:
                    decision = (level, f"Stop-loss hit ({strategy.stopLossPct:g}% below entry)")
            if decision is None and tp is not None:
                level = pos["price"] * (1 + tp)
                if opens[i] >= level:
                    decision = (opens[i], f"Take-profit hit ({strategy.takeProfitPct:g}% above entry)")
                elif highs[i] >= level:
                    decision = (level, f"Take-profit hit ({strategy.takeProfitPct:g}% above entry)")
            if decision is None and strategy.exitDays is not None and i - pos["entry_idx"] >= strategy.exitDays:
                decision = (closes[i], f"{strategy.exitDays} trading days reached")
            if decision is None and i == last_idx:
                decision = (closes[i], "Backtest period ended")
                warnings.append(f"A trade was closed early on {dates[i]} because the backtest period ended.")
            if decision is None and exit_conds and all(_holds(c.operator, l, r, i) for c, l, r in exit_conds):
                if at_signal_close:
                    decision = (closes[i], signal_exit_text)
                else:
                    pos["exit_signal"] = True
            if decision:
                close_trade(i, *decision)
                exited_now = True

        # With same-close fills, don't sell and re-buy on the same bar.
        if pos is None and not (exited_now and at_signal_close) and in_range[i] \
                and all(_holds(c.operator, l, r, i) for c, l, r in entry_conds):
            entry_idx = i if at_signal_close else i + 1
            if entry_idx < last_idx:  # needs room for at least one bar after entry
                pos = {
                    "entry_idx": entry_idx, "filled": False, "exit_signal": False,
                    "shares": 0.0, "price": 0.0, "cost": 0.0,
                    "reasons": [f"{condition_label(c)} ({OP_TEXT[c.operator][0]})" for c, _, _ in entry_conds],
                }
                if at_signal_close:
                    fill_entry(closes[i])

        if in_range[i]:
            held = pos["shares"] * closes[i] if pos and pos["filled"] else 0.0
            equity.append((dates[i], cash + held))

    bench = [(dates[i], strategy.initialCapital * closes[i] / closes[first_idx]) for i in range(first_idx, last_idx + 1)]
    return _summarize(strategy, trades, equity, bench, warnings, str(df.attrs.get("currency", "USD")))


def _summarize(strategy: Strategy, trades: list[Trade], equity: list[tuple[str, float]],
               bench: list[tuple[str, float]], warnings: list[str], currency: str) -> BacktestResult:
    wins = [t for t in trades if t.result == "WIN"]
    losses = [t for t in trades if t.result == "LOSS"]
    mean = lambda xs: float(np.mean(xs)) if len(xs) else 0.0  # noqa: E731
    gross_win = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)

    values = np.array([v for _, v in equity])
    total = values[-1] / strategy.initialCapital - 1
    days = (datetime.fromisoformat(equity[-1][0]) - datetime.fromisoformat(equity[0][0])).days
    years = max(days / 365.25, 1 / 365)
    cagr = (1 + total) ** (1 / years) - 1 if total > -1 else -1.0

    max_dd = float(np.min(values / np.maximum.accumulate(values) - 1))
    rets = values[1:] / values[:-1] - 1
    sd = float(np.std(rets)) if len(rets) else 0.0
    sharpe = float(np.mean(rets)) / sd * math.sqrt(252) if sd > 0 else None

    _b = np.array([v for _, v in bench])
    return BacktestResult(
        strategy=strategy,
        totalReturnPct=_r2(total * 100), cagrPct=_r2(cagr * 100),
        winRatePct=_r2(len(wins) / len(trades) * 100) if trades else 0.0,
        profitFactor=_r2(gross_win / gross_loss) if gross_loss > 0 else None,
        maxDrawdownPct=_r2(max_dd * 100),
        sharpeRatio=_r2(sharpe) if sharpe is not None else None,
        totalTrades=len(trades), winningTrades=len(wins), losingTrades=len(losses),
        avgTradeReturnPct=_r2(mean([t.returnPct for t in trades])),
        avgWinReturnPct=_r2(mean([t.returnPct for t in wins])),
        avgLossReturnPct=_r2(mean([t.returnPct for t in losses])),
        buyHoldReturnPct=_r2((bench[-1][1] / bench[0][1] - 1) * 100),
        buyHoldMaxDrawdownPct=_r2(float(np.min(_b / np.maximum.accumulate(_b) - 1)) * 100),
        equityCurve=[EquityPoint(date=d, value=_r2(v)) for d, v in equity],
        benchmarkCurve=[EquityPoint(date=d, value=_r2(v)) for d, v in bench],
        trades=trades, warnings=warnings, currency=currency,
    )
