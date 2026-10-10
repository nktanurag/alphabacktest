import { fmtDate, fmtMoney, fmtPct, fmtPrice, tone } from "../format";
import type { Trade } from "../types";
import { useEscape } from "./ui";

export default function TradeDrawer({ trade, currency, onClose }: { trade: Trade; currency: string; onClose: () => void }) {
  useEscape(onClose);
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={onClose}>
      <aside role="dialog" aria-label={`Trade ${trade.id}`} onClick={(e) => e.stopPropagation()}
        className="w-full sm:max-w-md h-full overflow-y-auto bg-surface border-l border-white/10 p-6 space-y-6">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">Trade</div>
            <h2 className="text-lg font-semibold font-mono">#{String(trade.id).padStart(3, "0")}</h2>
          </div>
          <button onClick={onClose} aria-label="Close" className="text-slate-500 hover:text-slate-200 text-xl leading-none">×</button>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Cell label="Result"><span className={`font-semibold ${trade.result === "WIN" ? "text-success" : "text-danger"}`}>{trade.result}</span></Cell>
          <Cell label="Return"><span className={tone(trade.returnPct)}>{fmtPct(trade.returnPct)}</span></Cell>
          <Cell label="P&L"><span className={tone(trade.pnl)}>{fmtMoney(trade.pnl, currency, true)}</span></Cell>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Cell label="Entry">{fmtDate(trade.entryDate)}<div className="text-slate-400">{fmtPrice(trade.entryPrice, currency)}</div></Cell>
          <Cell label="Exit">{fmtDate(trade.exitDate)}<div className="text-slate-400">{fmtPrice(trade.exitPrice, currency)}</div></Cell>
        </div>
        <p className="text-sm text-slate-400">Holding period: {trade.holdingDays} trading days</p>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Why did this trade trigger?</h3>
          <ul className="space-y-1.5 text-sm">
            {trade.entryReasons.map((r) => <li key={r} className="flex gap-2"><span className="text-success">✓</span>{r}</li>)}
          </ul>
        </div>
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Exit</h3>
          <p className="text-sm flex gap-2"><span className="text-success">✓</span>{trade.exitReason}</p>
        </div>
      </aside>
    </div>
  );
}

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-field border border-white/8 rounded-lg px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">{label}</div>
      <div className="font-mono text-sm">{children}</div>
    </div>
  );
}
