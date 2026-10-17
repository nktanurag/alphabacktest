import { useEffect, type ButtonHTMLAttributes, type ReactNode } from "react";

/** Call `onEscape` when the Escape key is pressed while the component is mounted. */
export function useEscape(onEscape: () => void) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onEscape();
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onEscape]);
}

export const inputCls =
  "w-full bg-field border border-white/10 rounded-lg px-3 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20";

export function Button({ variant = "secondary", className = "", ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" }) {
  const styles = {
    primary: "bg-primary hover:brightness-110 text-on-primary disabled:bg-primary/30 disabled:text-on-primary/70",
    secondary: "border border-white/10 text-slate-300 hover:bg-white/5 disabled:opacity-40",
    danger: "bg-danger/10 border border-danger/25 text-danger hover:bg-danger/15",
    ghost: "text-slate-400 hover:text-slate-200 hover:bg-white/5",
  }[variant];
  return <button {...p} className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:cursor-not-allowed ${styles} ${className}`} />;
}

export function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="bg-surface rounded-xl border border-white/8">
      <div className="px-5 py-3.5 border-b border-white/8 flex items-center justify-between">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{title}</h2>
        {aside}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="block text-[10px] font-semibold text-slate-500 uppercase tracking-widest mb-1.5">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-slate-600 mt-1">{hint}</span>}
    </label>
  );
}

export function Stat({ label, value, className = "" }: { label: string; value: ReactNode; className?: string }) {
  return (
    <div className="bg-field border border-white/8 rounded-lg px-4 py-3">
      <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className={`mt-1 font-mono text-lg font-semibold ${className}`}>{value}</div>
    </div>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEscape(onClose);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60" onClick={onClose}>
      <div role="dialog" aria-label={title} className="w-full max-w-lg bg-surface border border-white/10 rounded-xl shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-white/8 text-sm font-semibold">{title}</div>
        {children}
      </div>
    </div>
  );
}
