export const fmtDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });

export const fmtPct = (n: number, signed = true) => `${signed && n > 0 ? "+" : ""}${n.toFixed(2)}%`;

const money = (n: number, currency: string, digits: number) =>
  Math.abs(n).toLocaleString("en-US", { style: "currency", currency, minimumFractionDigits: digits, maximumFractionDigits: digits });

/** Whole-unit amount in the asset's currency (USD, INR, ...). */
export const fmtMoney = (n: number, currency = "USD", signed = false) => {
  const s = money(n, currency, 0);
  return n < 0 ? `-${s}` : signed && n > 0 ? `+${s}` : s;
};

export const fmtPrice = (n: number, currency = "USD") => money(n, currency, 2);
export const tone = (n: number) => (n > 0 ? "text-success" : n < 0 ? "text-danger" : "text-slate-300");
