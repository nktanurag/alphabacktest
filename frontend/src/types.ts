// Mirrors backend/alphabacktest/models.py — keep in sync.
export type IndicatorName =
  | "SMA" | "EMA" | "RSI" | "BB_UPPER" | "BB_LOWER"
  | "MACD" | "MACD_SIGNAL" | "VOLUME" | "PRICE";

export type Operator = "crosses_above" | "crosses_below" | "greater_than" | "less_than" | "equals";

export interface IndicatorOperand { kind: "indicator"; name: IndicatorName; period?: number }
export interface ValueOperand { kind: "value"; value: number }
export type Operand = IndicatorOperand | ValueOperand;

export interface Condition {
  id: string;
  left: IndicatorOperand;
  operator: Operator;
  right: Operand;
}

export interface Strategy {
  name: string;
  asset: string;
  startDate: string;
  endDate: string;
  entryConditions: Condition[];
  /** Exit rules; the first one to trigger closes the trade. At least one is required. */
  exitDays: number | null;
  stopLossPct: number | null;
  takeProfitPct: number | null;
  /** Close the trade when ALL of these are true. */
  exitConditions: Condition[];
  entryTiming: "next_open" | "signal_close";
  initialCapital: number;
  positionSizePct: number;
  commissionPct: number;
  slippagePct: number;
}

export interface Trade {
  id: number;
  entryDate: string;
  entryPrice: number;
  exitDate: string;
  exitPrice: number;
  holdingDays: number;
  returnPct: number;
  pnl: number;
  result: "WIN" | "LOSS";
  entryReasons: string[];
  exitReason: string;
}

export interface EquityPoint { date: string; value: number }

export interface BacktestResult {
  strategy: Strategy;
  totalReturnPct: number;
  cagrPct: number;
  winRatePct: number;
  profitFactor: number | null;
  maxDrawdownPct: number;
  sharpeRatio: number | null;
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  avgTradeReturnPct: number;
  avgWinReturnPct: number;
  avgLossReturnPct: number;
  buyHoldReturnPct: number;
  buyHoldMaxDrawdownPct: number;
  equityCurve: EquityPoint[];
  benchmarkCurve: EquityPoint[];
  trades: Trade[];
  warnings: string[];
  /** Currency the asset trades in, e.g. USD, INR. */
  currency: string;
}
