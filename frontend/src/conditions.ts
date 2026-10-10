import type { Condition, IndicatorName, IndicatorOperand, Operand, Operator } from "./types";

export interface IndicatorDef {
  name: IndicatorName;
  label: string;
  /** "required" period, "optional" period (Volume average), or none. */
  period: "required" | "optional" | "none";
}

export const INDICATORS: IndicatorDef[] = [
  { name: "PRICE", label: "Price (Close)", period: "none" },
  { name: "SMA", label: "SMA", period: "required" },
  { name: "EMA", label: "EMA", period: "required" },
  { name: "RSI", label: "RSI", period: "required" },
  { name: "BB_UPPER", label: "Bollinger Upper", period: "required" },
  { name: "BB_LOWER", label: "Bollinger Lower", period: "required" },
  { name: "MACD", label: "MACD", period: "none" },
  { name: "MACD_SIGNAL", label: "MACD Signal Line", period: "none" },
  { name: "VOLUME", label: "Volume", period: "optional" },
];

export const OPERATORS: { value: Operator; label: string }[] = [
  { value: "crosses_above", label: "Crosses Above" },
  { value: "crosses_below", label: "Crosses Below" },
  { value: "greater_than", label: "Is Greater Than" },
  { value: "less_than", label: "Is Less Than" },
  { value: "equals", label: "Equals" },
];

export const defOf = (name: IndicatorName) => INDICATORS.find((i) => i.name === name)!;

const SHORT: Record<IndicatorName, string> = {
  PRICE: "Price", SMA: "SMA", EMA: "EMA", RSI: "RSI", BB_UPPER: "BB Upper", BB_LOWER: "BB Lower",
  MACD: "MACD", MACD_SIGNAL: "MACD Signal", VOLUME: "Volume",
};

export function operandLabel(o: Operand): string {
  if (o.kind === "value") return String(o.value);
  return o.period ? `${SHORT[o.name]}(${o.period})` : SHORT[o.name];
}

export const operatorLabel = (op: Operator) => OPERATORS.find((o) => o.value === op)!.label;

/** Returns an error message if the condition can't be sent to the backend. */
export function validateCondition(c: Condition): string | null {
  const check = (o: IndicatorOperand): string | null => {
    const d = defOf(o.name);
    if (d.period === "required" && !(Number.isInteger(o.period) && o.period! > 0)) return "Enter a valid period (greater than 0).";
    if (d.period === "optional" && o.period !== undefined && !(Number.isInteger(o.period) && o.period > 0)) return "Period must be greater than 0.";
    return null;
  };
  const l = check(c.left);
  if (l) return l;
  if (c.right.kind === "value") return Number.isFinite(c.right.value) ? null : "Enter a comparison value.";
  return check(c.right);
}

export const newId = () => Math.random().toString(36).slice(2, 9);
