from typing import Literal, Optional, Union
from pydantic import BaseModel, Field

IndicatorName = Literal["SMA", "EMA", "RSI", "BB_UPPER", "BB_LOWER", "MACD", "MACD_SIGNAL", "VOLUME", "PRICE"]
Operator = Literal["crosses_above", "crosses_below", "greater_than", "less_than", "equals"]


class Indicator(BaseModel):
    kind: Literal["indicator"] = "indicator"
    name: IndicatorName
    period: Optional[int] = Field(default=None, gt=0)


class Value(BaseModel):
    kind: Literal["value"] = "value"
    value: float


Operand = Union[Indicator, Value]


class Condition(BaseModel):
    id: str
    left: Indicator
    operator: Operator
    right: Operand


class Strategy(BaseModel):
    name: str = Field(min_length=1)
    asset: str = Field(min_length=1)
    startDate: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    endDate: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    # MVP: all entry conditions are ANDed.
    entryConditions: list[Condition]
    # Exit rules. The first one that triggers closes the trade; at least one is required.
    # Fixed holding period in trading days (None = no time limit).
    exitDays: Optional[int] = None
    # Stop-loss / take-profit as a percent from the entry price (5 = 5%). None = off.
    stopLossPct: Optional[float] = None
    takeProfitPct: Optional[float] = None
    # Signal exit: close the trade when ALL of these are true (same condition format as entry).
    exitConditions: list[Condition] = []
    # next_open: fill at the next bar's open (default). signal_close: fill at the signal bar's close.
    entryTiming: Literal["next_open", "signal_close"] = "next_open"
    initialCapital: float
    positionSizePct: float
    commissionPct: float
    slippagePct: float


class Trade(BaseModel):
    id: int
    entryDate: str
    entryPrice: float
    exitDate: str
    exitPrice: float
    holdingDays: int
    returnPct: float
    pnl: float
    result: Literal["WIN", "LOSS"]
    entryReasons: list[str]
    exitReason: str


class EquityPoint(BaseModel):
    date: str
    value: float


class BacktestResult(BaseModel):
    strategy: Strategy
    totalReturnPct: float
    cagrPct: float
    winRatePct: float
    profitFactor: Optional[float]
    maxDrawdownPct: float
    sharpeRatio: Optional[float]
    totalTrades: int
    winningTrades: int
    losingTrades: int
    avgTradeReturnPct: float
    avgWinReturnPct: float
    avgLossReturnPct: float
    # Buy-and-hold of the same asset over the same period (before costs), for comparison.
    buyHoldReturnPct: float = 0.0
    buyHoldMaxDrawdownPct: float = 0.0
    equityCurve: list[EquityPoint] = []
    benchmarkCurve: list[EquityPoint] = []
    trades: list[Trade]
    warnings: list[str]
    # Currency the asset trades in (e.g. USD, INR), for display.
    currency: str = "USD"
