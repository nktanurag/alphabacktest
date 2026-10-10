import { useState } from "react";
import { operandLabel, operatorLabel } from "../conditions";
import type { Condition } from "../types";
import { Button } from "./ui";

function Row({ c, index, onEdit, onDelete }: { c: Condition; index: number; onEdit: () => void; onDelete: () => void }) {
  const [confirming, setConfirming] = useState(false);
  return (
    <div onClick={() => !confirming && onEdit()} className="group flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 rounded-lg border border-white/8 bg-field hover:border-white/15 cursor-pointer">
      <span className="font-mono text-[11px] text-slate-600 w-5">{String(index + 1).padStart(2, "0")}</span>
      <div className="flex-1 flex items-center gap-2 flex-wrap min-w-0 text-xs">
        <span className="px-2 py-1 rounded-md bg-primary/10 text-primary border border-primary/20 font-mono">{operandLabel(c.left)}</span>
        <span className="text-slate-500">{operatorLabel(c.operator)}</span>
        <span className="px-2 py-1 rounded-md bg-white/5 text-slate-200 border border-white/8 font-mono">{operandLabel(c.right)}</span>
      </div>
      <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
        {confirming ? (
          <>
            <span className="text-xs text-slate-400 mr-1">Remove this condition?</span>
            <Button variant="ghost" className="!px-2 !py-1 text-xs" onClick={() => setConfirming(false)}>Cancel</Button>
            <Button variant="danger" className="!px-2 !py-1 text-xs" onClick={onDelete}>Remove</Button>
          </>
        ) : (
          <>
            <Button variant="ghost" className="!px-2 !py-1 text-xs" onClick={onEdit}>Edit</Button>
            <Button variant="ghost" className="!px-2 !py-1 text-xs hover:!text-danger" aria-label={`Delete condition ${index + 1}`} onClick={() => setConfirming(true)}>Delete</Button>
          </>
        )}
      </div>
    </div>
  );
}

export default function ConditionList({ conditions, onEdit, onDelete, onAdd, note = "ALL conditions must be true to open a position.",
  emptyTitle = "No entry conditions yet.", emptyHint = "Add conditions to define when a position should be opened.", compact = false }: {
  conditions: Condition[]; onEdit: (c: Condition) => void; onDelete: (id: string) => void; onAdd: () => void;
  note?: string; emptyTitle?: string; emptyHint?: string; compact?: boolean;
}) {
  if (conditions.length === 0) {
    return (
      <div className={compact ? "py-3" : "py-8 text-center"}>
        <p className="text-sm text-slate-300">{emptyTitle}</p>
        <p className="text-xs text-slate-500 mt-1 mb-3">{emptyHint}</p>
        <Button variant={compact ? "secondary" : "primary"} onClick={onAdd}>+ Add Condition</Button>
      </div>
    );
  }
  return (
    <div>
      <p className="text-xs text-slate-500 mb-3">{note}</p>
      <div className="max-h-[420px] overflow-y-auto pr-1">
        {conditions.map((c, i) => (
          <div key={c.id}>
            {i > 0 && (
              <div className="flex flex-col items-center py-1.5">
                <div className="w-px h-2 bg-white/10" />
                <span className="text-[9px] font-mono tracking-[0.25em] text-slate-600 px-2 py-0.5 border border-white/8 rounded">AND</span>
                <div className="w-px h-2 bg-white/10" />
              </div>
            )}
            <Row c={c} index={i} onEdit={() => onEdit(c)} onDelete={() => onDelete(c.id)} />
          </div>
        ))}
      </div>
      <Button className="mt-4 w-full" onClick={onAdd}>+ Add Condition</Button>
    </div>
  );
}
