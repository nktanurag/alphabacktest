import type { Strategy } from "../types";
import { Button } from "./ui";

export default function Running({ strategy, onCancel }: { strategy: Strategy; onCancel: () => void }) {
  return (
    <div className="min-h-full flex flex-col items-center justify-center gap-4 text-center px-4">
      <div className="h-10 w-10 rounded-full border-2 border-white/10 border-t-primary animate-spin" />
      <h1 className="text-lg font-semibold">Running backtest…</h1>
      <p className="text-sm text-slate-500 max-w-sm">
        Loading {strategy.asset} history and testing {strategy.entryConditions.length} entry condition
        {strategy.entryConditions.length === 1 ? "" : "s"}.
      </p>
      <Button variant="ghost" onClick={onCancel}>Cancel</Button>
    </div>
  );
}
