import { useMemo, useState } from "react";
import { operandLabel, operatorLabel } from "../conditions";
import { fmtDate, fmtMoney, fmtPct, fmtPrice, tone } from "../format";
import type { BacktestResult, Trade } from "../types";
import EquityChart from "./EquityChart";
import TradeDrawer from "./TradeDrawer";
import { Button, Section, Stat } from "./ui";

type SortKey = "id" | "entryDate" | "returnPct" | "pnl";

export function Failed({ message, onRetry, onEdit }: { message: string; onRetry: () => void; onEdit: () => void }) {
  return (
    <div className="min-h-full flex flex-col items-center justify-center gap-3 text-center px-4">
      <h1 className="text-lg font-semibold">Backtest could not be completed</h1>
      <p className="text-sm text-slate-500 max-w-sm">{message}</p>
      <div className="flex gap-2 mt-2"><Button variant="primary" onClick={onRetry}>Try Again</Button><Button onClick={onEdit}>Edit Strategy</Button></div>
    </div>
  );
}

export default function Results({ result, onEdit, onRunAgain, onSave }: { result: BacktestResult; onEdit: () => void; onRunAgain: () => void; onSave: () => void }) {
  const s = result.strategy;
  const cur = result.currency;
  const [filter, setFilter] = useState<"ALL" | "WIN" | "LOSS">("ALL");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "id", dir: 1 });
  const [open, setOpen] = useState<Trade | null>(null);

  const rows = useMemo(() => {
    const r = result.trades.filter((t) => filter === "ALL" || t.result === filter);
    return [...r].sort((a, b) => (a[sort.key] > b[sort.key] ? 1 : a[sort.key] < b[sort.key] ? -1 : 0) * sort.dir);
  }, [result.trades, filter, sort]);

  const header = (
    <header className="flex flex-wrap items-start justify-between gap-3 mb-6">
      <div>
        <div className="text-[10px] uppercase tracking-widest text-slate-500">Backtest results</div>
        <h1 className="text-xl font-semibold">{s.name || `${s.asset} strategy`}</h1>
        <p className="text-sm text-slate-500">{s.asset} · {fmtDate(s.startDate)} — {fmtDate(s.endDate)}</p>
      </div>
      <div className="flex gap-2"><Button onClick={onSave}>Save Strategy</Button><Button onClick={onEdit}>Edit Strategy</Button><Button variant="primary" onClick={onRunAgain}>Run Again</Button></div>
    </header>
  );

  if (result.totalTrades === 0) {
    return (
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        {header}
        <div className="text-center py-16">
          <h2 className="text-lg font-semibold">No trades generated</h2>
          <p className="text-sm text-slate-500 mt-1">Your strategy did not produce any entry signals during the selected historical period.</p>
          <p className="text-xs text-slate-600 mt-3">Try loosening a condition or widening the date range.</p>
        </div>
        <Warnings items={result.warnings} />
      </div>
    );
  }

  const th = (label: string, key?: SortKey, right = false) => (
    <th className={`px-3 py-2 font-medium ${right ? "text-right" : "text-left"}`}>
      {key ? (
        <button onClick={() => setSort((p) => ({ key, dir: p.key === key ? (-p.dir as 1 | -1) : 1 }))} className="hover:text-slate-200">
          {label}{sort.key === key ? (sort.dir === 1 ? " ↑" : " ↓") : ""}
        </button>
      ) : label}
    </th>
  );

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 space-y-6">
      {header}
      <Warnings items={result.warnings} />

      <Section title="Strategy">
        <div className="text-sm space-y-1 font-mono text-xs">
          {s.entryConditions.map((c, i) => (
            <div key={c.id}><span className="text-slate-600 mr-2">{i === 0 ? "   " : "AND"}</span>{operandLabel(c.left)} {operatorLabel(c.operator).toLowerCase()} {operandLabel(c.right)}</div>
          ))}
          <div className="text-slate-500 pt-1">Enter at {s.entryTiming === "signal_close" ? "the signal day's close" : "the next day's open"}</div>
          <div className="text-slate-500">
            Exit on the first of: {[
              s.exitDays !== null && `${s.exitDays} trading days`,
              s.stopLossPct !== null && `${s.stopLossPct}% stop-loss`,
              s.takeProfitPct !== null && `${s.takeProfitPct}% take-profit`,
              s.exitConditions.length > 0 && `signal (${s.exitConditions.map((c) => `${operandLabel(c.left)} ${operatorLabel(c.operator).toLowerCase()} ${operandLabel(c.right)}`).join(" AND ")})`,
            ].filter(Boolean).join(" · ")}
          </div>
        </div>
      </Section>

      <Section title="Equity Curve">
        <EquityChart strategy={result.equityCurve} benchmark={result.benchmarkCurve} currency={cur} />
      </Section>

      <Section title="Performance">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <Stat label="Total return" value={fmtPct(result.totalReturnPct)} className={tone(result.totalReturnPct)} />
          <Stat label="CAGR" value={fmtPct(result.cagrPct)} className={tone(result.cagrPct)} />
          <Stat label="Win rate" value={fmtPct(result.winRatePct, false)} />
          <Stat label="Profit factor" value={result.profitFactor?.toFixed(2) ?? "—"} />
          <Stat label="Max drawdown" value={fmtPct(result.maxDrawdownPct)} className="text-danger" />
          <Stat label="Sharpe ratio" value={result.sharpeRatio?.toFixed(2) ?? "—"} />
          <Stat label="Buy & hold return" value={fmtPct(result.buyHoldReturnPct)} className={tone(result.buyHoldReturnPct)} />
          <Stat label="Buy & hold drawdown" value={fmtPct(result.buyHoldMaxDrawdownPct)} className="text-danger" />
          <Stat label="vs buy & hold" value={`${fmtPct(Math.round((result.totalReturnPct - result.buyHoldReturnPct) * 100) / 100)} pts`} className={tone(result.totalReturnPct - result.buyHoldReturnPct)} />
        </div>
      </Section>

      <Section title="Trade Summary">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <Stat label="Total trades" value={result.totalTrades} />
          <Stat label="Winning trades" value={result.winningTrades} className="text-success" />
          <Stat label="Losing trades" value={result.losingTrades} className="text-danger" />
          <Stat label="Avg trade return" value={fmtPct(result.avgTradeReturnPct)} className={tone(result.avgTradeReturnPct)} />
          <Stat label="Avg winning trade" value={fmtPct(result.avgWinReturnPct)} className="text-success" />
          <Stat label="Avg losing trade" value={fmtPct(result.avgLossReturnPct)} className="text-danger" />
        </div>
      </Section>

      <Section title="Trades" aside={
        <div className="flex gap-1">
          {(["ALL", "WIN", "LOSS"] as const).map((f) => (
            <button key={f} onClick={() => setFilter(f)} className={`text-xs px-2.5 py-1 rounded-md ${filter === f ? "bg-primary/20 text-primary" : "text-slate-500 hover:text-slate-300"}`}>{f === "ALL" ? "All" : f === "WIN" ? "Wins" : "Losses"}</button>
          ))}
        </div>
      }>
        <div className="overflow-x-auto -mx-5 px-5">
          <table className="w-full text-sm min-w-[720px]">
            <thead className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-white/8">
              <tr>{th("#", "id")}{th("Entry date", "entryDate")}{th("Entry", undefined, true)}{th("Exit date")}{th("Exit", undefined, true)}{th("Days", undefined, true)}{th("Return", "returnPct", true)}{th("P&L", "pnl", true)}{th("Result")}</tr>
            </thead>
            <tbody className="font-mono text-xs">
              {rows.map((t) => (
                <tr key={t.id} onClick={() => setOpen(t)} className="border-b border-white/5 hover:bg-white/[.03] cursor-pointer">
                  <td className="px-3 py-2.5 text-slate-500">{String(t.id).padStart(3, "0")}</td>
                  <td className="px-3 py-2.5">{fmtDate(t.entryDate)}</td>
                  <td className="px-3 py-2.5 text-right">{fmtPrice(t.entryPrice, cur)}</td>
                  <td className="px-3 py-2.5">{fmtDate(t.exitDate)}</td>
                  <td className="px-3 py-2.5 text-right">{fmtPrice(t.exitPrice, cur)}</td>
                  <td className="px-3 py-2.5 text-right">{t.holdingDays}</td>
                  <td className={`px-3 py-2.5 text-right ${tone(t.returnPct)}`}>{fmtPct(t.returnPct)}</td>
                  <td className={`px-3 py-2.5 text-right ${tone(t.pnl)}`}>{fmtMoney(t.pnl, cur, true)}</td>
                  <td className="px-3 py-2.5"><span className={`px-1.5 py-0.5 rounded text-[10px] ${t.result === "WIN" ? "bg-success/10 text-success" : "bg-danger/10 text-danger"}`}>{t.result}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <p className="text-center text-sm text-slate-500 py-6">No trades match this filter.</p>}
        </div>
      </Section>

      {open && <TradeDrawer trade={open} currency={cur} onClose={() => setOpen(null)} />}
    </div>
  );
}

function Warnings({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="rounded-xl border border-warning/25 bg-warning/5 px-5 py-3 text-sm text-warning">
      <div className="font-medium">Backtest completed with warnings</div>
      <ul className="text-xs mt-1 list-disc pl-5">{items.map((w) => <li key={w}>{w}</li>)}</ul>
    </div>
  );
}
