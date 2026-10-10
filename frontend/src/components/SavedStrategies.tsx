import { useEffect, useState } from "react";
import { deleteStrategy, listStrategies, type SavedStrategy } from "../api";
import { fmtDate } from "../format";
import { Button } from "./ui";

export default function SavedStrategies({ onOpen, onNew, onBack }: {
  onOpen: (s: SavedStrategy) => void; onNew: () => void; onBack: () => void;
}) {
  const [items, setItems] = useState<SavedStrategy[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);

  const load = () => {
    setError(null); setItems(null);
    listStrategies().then(setItems).catch((e: Error) => setError(e.message));
  };
  useEffect(load, []);

  const remove = async (id: number) => {
    try { await deleteStrategy(id); setItems((p) => p?.filter((s) => s.id !== id) ?? null); setConfirming(null); }
    catch (e) { setError((e as Error).message); }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
      <header className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-xl font-semibold">Saved Strategies</h1>
          <p className="text-sm text-slate-500">{items ? `${items.length} saved` : " "}</p>
        </div>
        <div className="flex gap-2"><Button onClick={onBack}>Back to builder</Button><Button variant="primary" onClick={onNew}>+ New Strategy</Button></div>
      </header>

      {error && (
        <div role="alert" className="mb-4 rounded-xl border border-danger/25 bg-danger/5 px-5 py-3 text-sm text-danger flex items-center justify-between">
          {error}<Button variant="ghost" onClick={load}>Retry</Button>
        </div>
      )}
      {items === null && !error && <p className="text-sm text-slate-500">Loading…</p>}
      {items?.length === 0 && (
        <div className="text-center py-16">
          <p className="text-sm text-slate-300">No saved strategies yet.</p>
          <p className="text-xs text-slate-500 mt-1 mb-4">Build a strategy and click Save to find it here.</p>
          <Button variant="primary" onClick={onNew}>+ New Strategy</Button>
        </div>
      )}

      <ul className="space-y-3">
        {items?.map((s) => {
          const d = s.definition;
          const n = d.entryConditions.length;
          return (
            <li key={s.id} className="bg-surface border border-white/8 rounded-xl px-5 py-4 flex flex-wrap items-center gap-4">
              <div className="flex-1 min-w-[200px]">
                <div className="font-medium">{s.name}</div>
                {s.description && <div className="text-xs text-slate-500 mt-0.5 line-clamp-2">{s.description}</div>}
                <div className="text-xs text-slate-500 mt-1.5 font-mono">
                  {d.asset} · {n} condition{n === 1 ? "" : "s"} · {fmtDate(d.startDate)} — {fmtDate(d.endDate)}
                </div>
                <div className="text-[11px] text-slate-600 mt-1">Updated {new Date(s.updatedAt).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}</div>
              </div>
              {confirming === s.id ? (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-400">Delete this strategy?</span>
                  <Button variant="ghost" onClick={() => setConfirming(null)}>Cancel</Button>
                  <Button variant="danger" onClick={() => remove(s.id)}>Delete</Button>
                </div>
              ) : (
                <div className="flex gap-2">
                  <Button variant="primary" onClick={() => onOpen(s)}>Open</Button>
                  <Button variant="ghost" aria-label={`Delete ${s.name}`} onClick={() => setConfirming(s.id)}>Delete</Button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
