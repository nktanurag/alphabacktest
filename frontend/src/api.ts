import type { BacktestResult, Condition, Strategy } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    /** "invalid" = fixable by the user; "failed" = show the failed screen. */
    public kind: "invalid" | "failed",
    public issues: string[] = [],
  ) {
    super(message);
  }
}

export async function runBacktest(strategy: Strategy, signal?: AbortSignal): Promise<BacktestResult> {
  let res: Response;
  try {
    res = await fetch("/api/backtest", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(strategy),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("Could not reach the backtest service.", "failed");
  }
  if (res.ok) return res.json();

  const body = await res.json().catch(() => ({}));
  if (res.status === 400 && Array.isArray(body.issues)) {
    throw new ApiError("Invalid strategy", "invalid", body.issues);
  }
  // Never surface raw backend errors; use the friendly message when the API provides one.
  const friendly = res.status === 502 || res.status === 422 ? body.message : undefined;
  throw new ApiError(friendly ?? "The backtest could not be completed.", "failed");
}

export interface SymbolHit { symbol: string; name: string; exchange: string; type: string }

export async function searchSymbols(q: string, signal?: AbortSignal): Promise<SymbolHit[]> {
  const res = await fetch(`/api/symbols/search?q=${encodeURIComponent(q)}`, { signal });
  if (!res.ok) throw new Error("search failed");
  return res.json();
}

// ── Saved strategies ──────────────────────────────────────────────────────────

export interface SavedStrategy {
  id: number;
  name: string;
  description: string | null;
  definition: Strategy;
  createdAt: string;
  updatedAt: string;
}

/** The backend returns `period: null` for absent periods; the UI uses `undefined`. */
function normalize(s: SavedStrategy): SavedStrategy {
  const clean = <T extends { period?: number | null }>(o: T): T => {
    if (o.period == null) { const { period: _p, ...rest } = o; return rest as T; }
    return o;
  };
  const cleanCondition = (c: Condition): Condition => ({
    ...c,
    left: clean(c.left),
    right: c.right.kind === "indicator" ? clean(c.right) : c.right,
  });
  return {
    ...s,
    definition: {
      ...s.definition,
      entryConditions: s.definition.entryConditions.map(cleanCondition),
      exitConditions: (s.definition.exitConditions ?? []).map(cleanCondition),
    },
  };
}

async function strategiesCall<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/strategies${path}`, { headers: { "content-type": "application/json" }, ...init });
  } catch {
    throw new Error("Could not reach the server.");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail?.message ?? "Something went wrong. Please try again.");
  }
  return body as T;
}

export const listStrategies = async () => (await strategiesCall<SavedStrategy[]>("")).map(normalize);

export const saveStrategy = async (
  id: number | null, name: string, description: string, definition: Strategy,
): Promise<SavedStrategy> =>
  normalize(await strategiesCall<SavedStrategy>(id == null ? "" : `/${id}`, {
    method: id == null ? "POST" : "PUT",
    body: JSON.stringify({ name, description: description || null, definition }),
  }));

export const deleteStrategy = (id: number) => strategiesCall<void>(`/${id}`, { method: "DELETE" });
