import { useEffect, useRef, useState } from "react";
import { searchSymbols, type SymbolHit } from "../api";
import { inputCls } from "./ui";

/** Searchable stock dropdown: type a ticker or company name, pick a result. */
export default function SymbolPicker({ value, onChange }: { value: string; onChange: (symbol: string) => void }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SymbolHit[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);

  // Debounced search; stale requests are aborted.
  useEffect(() => {
    if (!open || !query.trim()) { setHits([]); setStatus("idle"); return; }
    const ctrl = new AbortController();
    setStatus("loading");
    const t = setTimeout(() => {
      searchSymbols(query, ctrl.signal)
        .then((r) => { setHits(r); setActive(0); setStatus("idle"); })
        .catch((e) => { if (e.name !== "AbortError") setStatus("error"); });
    }, 250);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [query, open]);

  useEffect(() => {
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const pick = (h: SymbolHit) => { onChange(h.symbol); setOpen(false); setQuery(""); };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, hits.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter" && hits[active]) { e.preventDefault(); pick(hits[active]); }
    else if (e.key === "Escape") setOpen(false);
  };

  return (
    <div ref={box} className="relative">
      {open ? (
        <input autoFocus className={inputCls} placeholder="Search ticker or company…" value={query}
          onChange={(e) => setQuery(e.target.value)} onKeyDown={onKey}
          role="combobox" aria-expanded aria-controls="symbol-list" />
      ) : (
        <button type="button" className={`${inputCls} text-left flex items-center justify-between`} onClick={() => setOpen(true)}>
          <span className={value ? "font-mono" : "text-slate-600"}>{value || "Select a stock"}</span>
          <span className="text-slate-500 text-xs">▾</span>
        </button>
      )}
      {open && (
        <ul id="symbol-list" role="listbox" className="absolute z-30 mt-1 w-full min-w-[260px] max-h-72 overflow-y-auto rounded-lg border border-white/10 bg-surface shadow-2xl">
          {status === "loading" && <li className="px-3 py-2.5 text-xs text-slate-500">Searching…</li>}
          {status === "error" && <li className="px-3 py-2.5 text-xs text-danger">Search is unavailable right now.</li>}
          {status === "idle" && !query.trim() && <li className="px-3 py-2.5 text-xs text-slate-500">Type to search stocks and ETFs.</li>}
          {status === "idle" && query.trim() && hits.length === 0 && <li className="px-3 py-2.5 text-xs text-slate-500">No matches.</li>}
          {hits.map((h, i) => (
            <li key={h.symbol} role="option" aria-selected={i === active} onMouseEnter={() => setActive(i)} onMouseDown={() => pick(h)}
              className={`px-3 py-2 cursor-pointer text-sm ${i === active ? "bg-primary/15" : ""}`}>
              <div className="flex justify-between gap-3">
                <span className="font-mono font-medium">{h.symbol}</span>
                <span className="text-[11px] text-slate-500 shrink-0">{h.exchange}</span>
              </div>
              <div className="text-xs text-slate-500 truncate">{h.name}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
