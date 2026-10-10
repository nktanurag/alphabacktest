import { useRef, useState } from "react";
import { ApiError, runBacktest, saveStrategy, type SavedStrategy } from "./api";
import { newId } from "./conditions";
import Results, { Failed } from "./components/Results";
import Running from "./components/Running";
import SaveDialog from "./components/SaveDialog";
import SavedStrategies from "./components/SavedStrategies";
import StrategyBuilder from "./components/StrategyBuilder";
import type { BacktestResult, Strategy } from "./types";

const DEFAULT_STRATEGY: Strategy = {
  name: "My Strategy",
  asset: "TSLA",
  startDate: "2022-01-01",
  endDate: "2024-12-31",
  entryConditions: [
    { id: newId(), left: { kind: "indicator", name: "RSI", period: 14 }, operator: "less_than", right: { kind: "value", value: 35 } },
  ],
  exitDays: 14,
  stopLossPct: null,
  takeProfitPct: null,
  exitConditions: [],
  entryTiming: "next_open",
  initialCapital: 100000,
  positionSizePct: 100,
  commissionPct: 0.1,
  slippagePct: 0.1,
};

type View =
  | { name: "builder" }
  | { name: "running" }
  | { name: "results"; result: BacktestResult }
  | { name: "failed"; message: string }
  | { name: "saved" };

export default function App() {
  const [strategy, setStrategy] = useState<Strategy>(DEFAULT_STRATEGY);
  const [view, setView] = useState<View>({ name: "builder" });
  const [serverIssues, setServerIssues] = useState<string[]>([]);
  const abort = useRef<AbortController | null>(null);
  // The saved strategy currently being edited (null = a new, unsaved one).
  const [saved, setSaved] = useState<{ id: number; description: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const run = async () => {
    abort.current?.abort();
    const ctrl = (abort.current = new AbortController());
    setServerIssues([]);
    setView({ name: "running" });
    try {
      const result = await runBacktest(strategy, ctrl.signal);
      setView({ name: "results", result });
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      if (e instanceof ApiError && e.kind === "invalid") {
        setServerIssues(e.issues);
        setView({ name: "builder" });
      } else {
        setView({ name: "failed", message: e instanceof ApiError ? e.message : "The backtest could not be completed." });
      }
    }
  };

  const toBuilder = () => setView({ name: "builder" });

  const doSave = async (name: string, description: string) => {
    const definition = { ...strategy, name };
    const s = await saveStrategy(saved?.id ?? null, name, description, definition);
    setStrategy(definition);
    setSaved({ id: s.id, description: s.description ?? "" });
    setSaving(false);
    setToast(`Saved "${s.name}"`);
    setTimeout(() => setToast(null), 2500);
  };

  const open = (s: SavedStrategy) => {
    setStrategy(s.definition);
    setSaved({ id: s.id, description: s.description ?? "" });
    setServerIssues([]);
    toBuilder();
  };

  const startNew = () => {
    setStrategy({ ...DEFAULT_STRATEGY, entryConditions: [], name: "New Strategy" });
    setSaved(null);
    setServerIssues([]);
    toBuilder();
  };

  const tab = view.name === "saved" ? "saved" : "builder";
  const navBtn = (id: "builder" | "saved", label: string, onClick: () => void) => (
    <button onClick={onClick} aria-current={tab === id ? "page" : undefined}
      className={`px-3 py-1.5 rounded-md text-sm ${tab === id ? "bg-primary/15 text-primary" : "text-slate-400 hover:text-slate-200"}`}>{label}</button>
  );

  return (
    <div className="min-h-full">
      {view.name !== "running" && (
        <nav className="border-b border-white/8 bg-surface/60">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 h-12 flex items-center gap-4">
            <span className="font-semibold tracking-tight">AlphaBacktest</span>
            <div className="flex gap-1">
              {navBtn("builder", "Strategy Builder", toBuilder)}
              {navBtn("saved", "Saved Strategies", () => setView({ name: "saved" }))}
            </div>
          </div>
        </nav>
      )}
      {view.name === "builder" && (
        <StrategyBuilder strategy={strategy} onChange={(s) => { setServerIssues([]); setStrategy(s); }} onRun={run} onSave={() => setSaving(true)} serverIssues={serverIssues} />
      )}
      {view.name === "running" && <Running strategy={strategy} onCancel={() => { abort.current?.abort(); toBuilder(); }} />}
      {view.name === "results" && <Results result={view.result} onEdit={toBuilder} onRunAgain={run} onSave={() => setSaving(true)} />}
      {view.name === "saved" && <SavedStrategies onOpen={open} onNew={startNew} onBack={toBuilder} />}
      {view.name === "failed" && <Failed message={view.message} onRetry={run} onEdit={toBuilder} />}
      {saving && (
        <SaveDialog initialName={strategy.name} initialDescription={saved?.description ?? ""} isUpdate={saved !== null}
          onSave={doSave} onClose={() => setSaving(false)} />
      )}
      {toast && <div role="status" className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 rounded-lg bg-success/15 border border-success/30 text-success text-sm px-4 py-2">{toast}</div>}
    </div>
  );
}
