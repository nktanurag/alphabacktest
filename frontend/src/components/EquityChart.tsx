import { useEffect, useMemo, useRef, useState } from "react";
import { fmtDate, fmtMoney } from "../format";
import type { EquityPoint } from "../types";

// Categorical slots 1 and 2 of the reference palette (dark mode), validated against the surface.
const STRATEGY = "#3987e5";
const BENCH = "#d95926";
const SURFACE = "#0e0e20";
const H = 280;
const PAD = { l: 64, r: 16, t: 12, b: 28 };

function niceTicks(min: number, max: number, n = 6): number[] {
  const span = max - min || 1;
  const raw = span / (n - 1);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 2.5, 5, 10].find((m) => m * mag >= raw) ?? 10) * mag;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(v);
  return out;
}

const compact = (v: number, currency: string) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency, notation: "compact", maximumFractionDigits: 1 }).format(v);

export default function EquityChart({ strategy, benchmark, currency }: { strategy: EquityPoint[]; benchmark: EquityPoint[]; currency: string }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(800);
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => e && setW(Math.max(320, e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const n = strategy.length;
  const geo = useMemo(() => {
    const all = [...strategy, ...benchmark].map((p) => p.value);
    const ticks = niceTicks(Math.min(...all), Math.max(...all));
    const lo = Math.min(ticks[0] ?? 0, ...all), hi = Math.max(ticks.at(-1) ?? 1, ...all);
    const x = (i: number) => PAD.l + (n <= 1 ? 0 : (i / (n - 1)) * (w - PAD.l - PAD.r));
    const y = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo || 1)) * (H - PAD.t - PAD.b);
    const path = (pts: EquityPoint[]) => pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
    // ~5 evenly spaced date labels
    const xt = Array.from({ length: 5 }, (_, k) => Math.round((k / 4) * (n - 1)));
    return { ticks, x, y, sPath: path(strategy), bPath: path(benchmark), xt };
  }, [strategy, benchmark, w, n]);

  if (n < 2) return null;
  const last = n - 1;
  const hi = hover ?? null;

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const frac = (e.clientX - r.left - PAD.l) / (w - PAD.l - PAD.r);
    setHover(Math.min(last, Math.max(0, Math.round(frac * last))));
  };

  // Monthly sample for the accessible table view.
  const rows = strategy.map((p, i) => ({ p, b: benchmark[i], i })).filter(({ p }, k, a) => k === a.length - 1 || p.date.slice(0, 7) !== a[k + 1]?.p.date.slice(0, 7));

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <div className="flex gap-4 text-xs text-slate-300">
          <span className="flex items-center gap-1.5"><i className="inline-block w-4 h-0.5 rounded" style={{ background: STRATEGY }} />Strategy</span>
          <span className="flex items-center gap-1.5"><i className="inline-block w-4 h-0.5 rounded" style={{ background: BENCH }} />Buy &amp; hold</span>
        </div>
        <button onClick={() => setTable((t) => !t)} className="text-xs text-slate-500 hover:text-slate-300">{table ? "Show chart" : "View as table"}</button>
      </div>

      {table ? (
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-xs font-mono">
            <thead className="text-slate-500 text-left"><tr><th className="py-1.5">Month end</th><th className="text-right">Strategy</th><th className="text-right">Buy &amp; hold</th></tr></thead>
            <tbody>{rows.map(({ p, b }) => <tr key={p.date} className="border-t border-white/5"><td className="py-1.5">{fmtDate(p.date)}</td><td className="text-right">{fmtMoney(p.value, currency)}</td><td className="text-right">{b ? fmtMoney(b.value, currency) : "—"}</td></tr>)}</tbody>
          </table>
        </div>
      ) : (
        <div ref={wrap} className="relative">
          <svg width={w} height={H} role="img" aria-label="Equity curve: strategy versus buy and hold" onMouseMove={onMove} onMouseLeave={() => setHover(null)} className="block">
            {geo.ticks.map((t) => (
              <g key={t}>
                <line x1={PAD.l} x2={w - PAD.r} y1={geo.y(t)} y2={geo.y(t)} stroke="rgba(255,255,255,.07)" strokeWidth={1} />
                <text x={PAD.l - 8} y={geo.y(t) + 4} textAnchor="end" fontSize={11} fill="#94a3b8">{compact(t, currency)}</text>
              </g>
            ))}
            {geo.xt.map((i) => (
              <text key={i} x={geo.x(i)} y={H - 8} textAnchor={i === 0 ? "start" : i === last ? "end" : "middle"} fontSize={11} fill="#94a3b8">
                {new Date(`${strategy[i]!.date}T12:00:00`).toLocaleDateString("en-GB", { month: "short", year: "2-digit" })}
              </text>
            ))}
            <path d={`${geo.sPath}L${geo.x(last)},${geo.y(geo.ticks[0] ?? 0)}L${geo.x(0)},${geo.y(geo.ticks[0] ?? 0)}Z`} fill={STRATEGY} opacity={0.1} />
            <path d={geo.bPath} fill="none" stroke={BENCH} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            <path d={geo.sPath} fill="none" stroke={STRATEGY} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            {[{ pts: benchmark, c: BENCH }, { pts: strategy, c: STRATEGY }].map(({ pts, c }) => {
              const i = hi ?? last;
              const p = pts[i];
              return p && <circle key={c} cx={geo.x(i)} cy={geo.y(p.value)} r={4} fill={c} stroke={SURFACE} strokeWidth={2} />;
            })}
            {hi !== null && <line x1={geo.x(hi)} x2={geo.x(hi)} y1={PAD.t} y2={H - PAD.b} stroke="rgba(255,255,255,.25)" strokeWidth={1} />}
          </svg>
          {hi !== null && (
            <div className="pointer-events-none absolute top-2 z-10 rounded-lg border border-white/10 bg-surface px-3 py-2 text-xs shadow-xl"
              style={{ left: Math.min(Math.max(geo.x(hi) + 12, PAD.l), w - 190) }}>
              <div className="text-slate-400 mb-1">{fmtDate(strategy[hi]!.date)}</div>
              <div className="flex items-center gap-1.5 font-mono"><i className="w-2 h-2 rounded-full" style={{ background: STRATEGY }} />{fmtMoney(strategy[hi]!.value, currency)}</div>
              <div className="flex items-center gap-1.5 font-mono"><i className="w-2 h-2 rounded-full" style={{ background: BENCH }} />{fmtMoney(benchmark[hi]?.value ?? 0, currency)}</div>
            </div>
          )}
        </div>
      )}
      <p className="text-[11px] text-slate-600 mt-2">Buy &amp; hold is the same asset over the same dates, before costs.</p>
    </div>
  );
}
