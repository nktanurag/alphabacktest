export type Theme = "dark" | "light";

const KEY = "alphabacktest-theme";

/** Saved choice, else the system setting, else dark. Browser storage can be blocked, so every access is guarded. */
export function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "dark" || saved === "light") return saved;
  } catch { /* storage unavailable */ }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function applyTheme(theme: Theme, save = false): void {
  document.documentElement.dataset.theme = theme;
  if (!save) return;
  try { localStorage.setItem(KEY, theme); } catch { /* storage unavailable */ }
}
