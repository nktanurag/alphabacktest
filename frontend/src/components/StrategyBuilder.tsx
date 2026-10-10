import { useState } from "react";
import { operandLabel, operatorLabel } from "../conditions";
import { fmtDate } from "../format";
import type { Condition, Strategy } from "../types";
import ConditionList from "./ConditionList";
import ConditionModal from "./ConditionModal";
import SymbolPicker from "./SymbolPicker";
import { Button, Field, Section, inputCls } from "./ui";

/** Client-side checks; mirrors backend validate_strategy so users see problems before a request. */
export function strategyIssues(s: Strategy): string[] {
  const e: string[] = [];
  if (!s.asset.trim()) e.push("Select an asset.");
  if (!s.startDate || !s.endDate || s.startDate >= s.endDate) e.push("Start date must be before end date.");
  if (s.entryConditions.length === 0) e.push("Add at least one entry condition.");
  if (s.exitDays !== null && (!Number.isInteger(s.exitDays) || s.exitDays < 1)) e.push("Holding period must be a whole number of at least 1 trading day.");
  if (s.stopLossPct !== null && !(s.stopLossPct > 0 && s.stopLossPct < 100)) e.push("Stop-loss must be between 0 and 100%.");
  if (s.takeProfitPct !== null && !(s.takeProfitPct > 0)) e.push("Take-profit must be greater than 0%.");
  if (s.exitDays === null && s.stopLossPct === null && s.takeProfitPct === null && s.exitConditions.length === 0) e.push("Add at least one exit rule.");
  if (!(s.initialCapital > 0)) e.push("Initial capital must be greater than 0.");
  if (!(s.positionSizePct > 0 && s.positionSizePct <= 100)) e.push("Position size must be between 1 and 100%.");
  if (!(s.commissionPct >= 0) || !(s.slippagePct >= 0)) e.push("Commission and slippage cannot be negative.");
  return e;
}

export default function StrategyBuilder({ strategy, onChange, onRun, onSave, serverIssues }: {
  strategy: Strategy; onChange: (s: Strategy) => void; onRun: () => void; onSave: () => void; serverIssues: string[];
}) {
  const [modal, setModal] = useState<{ list: "entry" | "exit"; editing?: Condition } | null>(null);
  const [showIssues, setShowIssues] = useState(false);
  const set = <K extends keyof Strategy>(k: K, v: Strategy[K]) => onChange({ ...strategy, [k]: v });
  // Optional numeric rule: empty input means "off" (null).
  const optNum = (k: "exitDays" | "stopLossPct" | "takeProfitPct", step: string) => ({
    type: "number" as const, step, className: inputCls, placeholder: "Off", min: 0,
    value: strategy[k] ?? "",
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => set(k, e.target.value === "" ? null : Number(e.target.value)),
  });
  const num = (k: "initialCapital" | "positionSizePct" | "commissionPct" | "slippagePct") => ({
    type: "number" as const, step: "any" as const, className: inputCls, value: Number.isNaN(strategy[k]) ? "" : strategy[k],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => set(k, e.target.value === "" ? NaN : Number(e.target.value)),
  });

  const issues = strategyIssues(strategy);
  const saveCondition = (c: Condition) => {
    const key = modal?.list === "exit" ? "exitConditions" : "entryConditions";
    const list = strategy[key];
    set(key, list.some((x) => x.id === c.id) ? list.map((x) => (x.id === c.id ? c : x)) : [...list, c]);
    setModal(null);
  };
  const n = strategy.entryConditions.length;

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
      <header className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-xl font-semibold">New Strategy</h1>
          <p className="text-sm text-slate-500">Define a strategy and test it against historical data.</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={onSave}>Save Strategy</Button>
          <Button variant="primary" onClick={() => (issues.length ? setShowIssues(true) : onRun())}>Run Backtest</Button>
        </div>
      </header>

      {(showIssues && issues.length > 0 || serverIssues.length > 0) && (
        <div role="alert" className="mb-6 rounded-xl border border-danger/25 bg-danger/5 px-5 py-3 text-sm text-danger">
          <div className="font-medium mb-1">{(showIssues ? issues : serverIssues).length} issue(s) need your attention.</div>
          <ul className="list-disc pl-5 text-xs space-y-0.5">{(showIssues && issues.length ? issues : serverIssues).map((m) => <li key={m}>{m}</li>)}</ul>
        </div>
      )}

      <div className="grid lg:grid-cols-[1fr_340px] gap-6">
        <div className="space-y-6">
          <Section title="Asset & Historical Data">
            <div className="grid sm:grid-cols-3 gap-4">
              <div>
                <span className="block text-[10px] font-semibold text-slate-500 uppercase tracking-widest mb-1.5">Asset</span>
                <SymbolPicker value={strategy.asset} onChange={(v) => set("asset", v)} />
              </div>
              <Field label="Start date"><input className={inputCls} type="date" value={strategy.startDate} onChange={(e) => set("startDate", e.target.value)} /></Field>
              <Field label="End date"><input className={inputCls} type="date" value={strategy.endDate} onChange={(e) => set("endDate", e.target.value)} /></Field>
            </div>
            <p className="text-[11px] text-slate-600 mt-3">Daily bars, split/dividend adjusted.</p>
          </Section>

          <Section title="Entry Conditions" aside={<span className="text-xs text-slate-500">{n} condition{n === 1 ? "" : "s"}</span>}>
            <ConditionList
              conditions={strategy.entryConditions}
              onAdd={() => setModal({ list: "entry" })}
              onEdit={(c) => setModal({ list: "entry", editing: c })}
              onDelete={(id) => set("entryConditions", strategy.entryConditions.filter((c) => c.id !== id))}
            />
          </Section>

          <Section title="Exit Rules">
            <p className="text-xs text-slate-500 mb-4">A trade closes as soon as the first of these triggers. Leave a field empty to turn it off.</p>
            <div className="grid sm:grid-cols-3 gap-4">
              <Field label="Holding period (trading days)"><input {...optNum("exitDays", "1")} /></Field>
              <Field label="Stop-loss (%)" hint="Sell if price falls this far below entry."><input {...optNum("stopLossPct", "any")} /></Field>
              <Field label="Take-profit (%)" hint="Sell if price rises this far above entry."><input {...optNum("takeProfitPct", "any")} /></Field>
            </div>
            <div className="mt-5 pt-5 border-t border-white/8">
              <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest mb-3">Exit signal</div>
              <ConditionList
                compact
                conditions={strategy.exitConditions}
                note="Close the trade when ALL of these are true."
                emptyTitle="No exit signal."
                emptyHint="Optionally close a trade when conditions become true, e.g. RSI(14) rises above 70."
                onAdd={() => setModal({ list: "exit" })}
                onEdit={(c) => setModal({ list: "exit", editing: c })}
                onDelete={(id) => set("exitConditions", strategy.exitConditions.filter((c) => c.id !== id))}
              />
            </div>
          </Section>

          <Section title="Strategy Summary">
            <dl className="text-sm grid grid-cols-[110px_1fr] gap-y-2">
              <dt className="text-slate-500">Asset</dt><dd>{strategy.asset || "—"} · Daily</dd>
              <dt className="text-slate-500">Period</dt><dd>{strategy.startDate && strategy.endDate ? `${fmtDate(strategy.startDate)} — ${fmtDate(strategy.endDate)}` : "—"}</dd>
              <dt className="text-slate-500">Entry</dt>
              <dd>
                {n === 0 ? "—" : (
                  <ol className="space-y-1">
                    {strategy.entryConditions.map((c, i) => (
                      <li key={c.id} className="font-mono text-xs">
                        <span className="text-slate-600 mr-2">{i === 0 ? "  " : "AND"}</span>
                        {operandLabel(c.left)} {operatorLabel(c.operator).toLowerCase()} {operandLabel(c.right)}
                      </li>
                    ))}
                  </ol>
                )}
              </dd>
              <dt className="text-slate-500">Exit</dt>
              <dd className="space-y-0.5">
                {strategy.exitDays !== null && <div>After {strategy.exitDays} trading days</div>}
                {strategy.stopLossPct !== null && <div>Stop-loss {strategy.stopLossPct}% below entry</div>}
                {strategy.takeProfitPct !== null && <div>Take-profit {strategy.takeProfitPct}% above entry</div>}
                {strategy.exitConditions.length > 0 && (
                  <div className="font-mono text-xs">Signal: {strategy.exitConditions.map((c) => `${operandLabel(c.left)} ${operatorLabel(c.operator).toLowerCase()} ${operandLabel(c.right)}`).join(" AND ")}</div>
                )}
                {issues.some((m) => m.includes("exit rule")) && <div className="text-slate-600">—</div>}
              </dd>
              <dt className="text-slate-500">Execution</dt>
              <dd>{(strategy.initialCapital || 0).toLocaleString()} capital · {strategy.entryTiming === "signal_close" ? "enter at signal close" : "enter at next open"} · {strategy.positionSizePct}% position · {strategy.commissionPct}% commission · {strategy.slippagePct}% slippage</dd>
            </dl>
          </Section>
        </div>

        <aside className="space-y-6 lg:sticky lg:top-6 self-start">
          <Section title="Execution Settings">
            <div className="space-y-4">
              <Field label="Initial capital"><input {...num("initialCapital")} min={1} /></Field>
              <Field label="Position size (%)"><input {...num("positionSizePct")} min={1} max={100} /></Field>
              <Field label="Entry timing" hint={strategy.entryTiming === "signal_close" ? "Buy at the close of the day the signal appears. Slightly optimistic: the signal needs that close." : "Buy at the open of the day after the signal. Avoids look-ahead bias."}>
                <select className={inputCls} value={strategy.entryTiming} onChange={(e) => set("entryTiming", e.target.value as Strategy["entryTiming"])}>
                  <option value="next_open">Next day's open</option>
                  <option value="signal_close">Signal day's close</option>
                </select>
              </Field>
              <Field label="Commission (%)" hint="Charged on entry and exit."><input {...num("commissionPct")} min={0} /></Field>
              <Field label="Slippage (%)" hint="Worsens each fill price."><input {...num("slippagePct")} min={0} /></Field>
            </div>
          </Section>
          <Section title="MVP Assumptions">
            <ul className="text-xs text-slate-500 space-y-1.5 list-disc pl-4">
              <li>Long-only, one position at a time.</li>
              <li>Signals (entry and exit) are evaluated on each day's close and filled per the entry-timing setting.</li>
              <li>Stop-loss and take-profit use each day's low/high; if both could hit in one day, the stop-loss is assumed first.</li>
              <li>A trade still open on the end date is closed that day.</li>
              <li>All entry conditions are combined with AND.</li>
            </ul>
          </Section>
        </aside>
      </div>

      {modal && <ConditionModal initial={modal.editing} onSave={saveCondition} onClose={() => setModal(null)} />}
    </div>
  );
}
