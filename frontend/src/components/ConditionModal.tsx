import { useState } from "react";
import { INDICATORS, OPERATORS, defOf, newId, validateCondition } from "../conditions";
import type { Condition, IndicatorName, Operator } from "../types";
import { Button, Field, Modal, inputCls } from "./ui";

/** Form state uses strings so empty/partial input is representable. */
interface Draft {
  leftName: IndicatorName;
  leftPeriod: string;
  operator: Operator;
  rightKind: "value" | IndicatorName;
  rightPeriod: string;
  rightValue: string;
}

function toDraft(c?: Condition): Draft {
  if (!c) return { leftName: "RSI", leftPeriod: "14", operator: "less_than", rightKind: "value", rightPeriod: "", rightValue: "30" };
  return {
    leftName: c.left.name, leftPeriod: c.left.period?.toString() ?? "", operator: c.operator,
    rightKind: c.right.kind === "value" ? "value" : c.right.name,
    rightPeriod: c.right.kind === "indicator" ? (c.right.period?.toString() ?? "") : "",
    rightValue: c.right.kind === "value" ? String(c.right.value) : "",
  };
}

function toCondition(d: Draft, id: string): Condition {
  const period = (s: string) => (s.trim() === "" ? undefined : Number(s));
  return {
    id,
    left: { kind: "indicator", name: d.leftName, period: period(d.leftPeriod) },
    operator: d.operator,
    right: d.rightKind === "value"
      ? { kind: "value", value: d.rightValue.trim() === "" ? NaN : Number(d.rightValue) }
      : { kind: "indicator", name: d.rightKind, period: period(d.rightPeriod) },
  };
}

function PeriodInput({ name, value, onChange }: { name: IndicatorName; value: string; onChange: (v: string) => void }) {
  const mode = defOf(name).period;
  if (mode === "none") return null;
  return (
    <Field label={mode === "optional" ? "Avg. period (optional)" : "Period"}>
      <input className={inputCls} type="number" min={1} step={1} value={value} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

export default function ConditionModal({ initial, onSave, onClose }: { initial?: Condition; onSave: (c: Condition) => void; onClose: () => void }) {
  const [d, setD] = useState<Draft>(() => toDraft(initial));
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((p) => ({ ...p, [k]: v }));
  const [touched, setTouched] = useState(false);

  const cond = toCondition(d, initial?.id ?? newId());
  const error = validateCondition(cond);

  return (
    <Modal title={initial ? "Edit condition" : "Add condition"} onClose={onClose}>
      <div className="p-5 space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Indicator">
            <select className={inputCls} value={d.leftName} onChange={(e) => {
              const name = e.target.value as IndicatorName;
              setD((p) => ({ ...p, leftName: name, leftPeriod: defOf(name).period === "required" ? p.leftPeriod || "14" : "" }));
            }}>
              {INDICATORS.map((i) => <option key={i.name} value={i.name}>{i.label}</option>)}
            </select>
          </Field>
          <PeriodInput name={d.leftName} value={d.leftPeriod} onChange={(v) => set("leftPeriod", v)} />
        </div>

        <Field label="Operator">
          <select className={inputCls} value={d.operator} onChange={(e) => set("operator", e.target.value as Operator)}>
            {OPERATORS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Compare with">
            <select className={inputCls} value={d.rightKind} onChange={(e) => {
              const k = e.target.value as Draft["rightKind"];
              setD((p) => ({ ...p, rightKind: k, rightPeriod: k !== "value" && defOf(k).period === "required" ? p.rightPeriod || "14" : "" }));
            }}>
              <option value="value">Fixed value</option>
              {INDICATORS.map((i) => <option key={i.name} value={i.name}>{i.label}</option>)}
            </select>
          </Field>
          {d.rightKind === "value" ? (
            <Field label="Value">
              <input className={inputCls} type="number" step="any" value={d.rightValue} onChange={(e) => set("rightValue", e.target.value)} />
            </Field>
          ) : (
            <PeriodInput name={d.rightKind} value={d.rightPeriod} onChange={(v) => set("rightPeriod", v)} />
          )}
        </div>

        {touched && error && <p className="text-xs text-danger">{error}</p>}
      </div>
      <div className="px-5 py-4 border-t border-white/8 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={() => (error ? setTouched(true) : onSave(cond))}>
          {initial ? "Save changes" : "Add condition"}
        </Button>
      </div>
    </Modal>
  );
}
