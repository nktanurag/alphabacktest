import { AuthRequired } from "./api";

export interface Doc {
  id: number; filename: string; status: "processing" | "ready" | "failed"; error: string | null;
  pageCount: number; chunkCount: number; sizeBytes: number; createdAt: string;
  embeddingModel: string | null; chunkWords: number | null; chunkOverlap: number | null;
  pdfTitle: string | null; pdfAuthor: string | null; pdfCreated: string | null;
  /** Made with a different embedding model than the server uses now; skipped in searches until re-uploaded. */
  stale: boolean;
}
export interface Chunk {
  chunkId: number; documentId: number; filename: string; page: number; section: string | null; text: string;
  /** Position in the "before reranking" list (vector and keyword results merged). */
  rank: number;
  /** Rank in the vector results; null when only the keyword search found it. */
  vectorRank: number | null; vectorScore: number;
  /** Rank in the keyword (BM25) results; null when the keyword search did not return it. */
  keywordRank: number | null; keywordScore: number | null;
  rerankRank: number | null; rerankScore: number | null;
}
/** candidates = before reranking (vector and keyword results merged); chunks = the final top results. */
export interface Answer {
  answer: string | null; answerError: string | null; candidates: Chunk[]; chunks: Chunk[];
  droppedBelowCutoff: number; minScore: number | null;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/docqa${path}`, init);
  } catch {
    throw new Error("Could not reach the server.");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (res.status === 401) throw new AuthRequired();
  if (!res.ok) throw new Error(body?.detail?.message ?? "Something went wrong. Please try again.");
  return body as T;
}

export interface DocqaConfig {
  enabled: boolean; minScore: number | null;
  chunkWords: number; chunkOverlap: number; minChunkWords: number; maxChunkWords: number;
  topK: number; maxTopK: number;
}
export interface ModelList { default: string; models: { id: string; name: string }[]; }
export const listModels = () => call<ModelList>("/models");
export const docqaConfig = () => call<DocqaConfig>("/config");
export const listDocs = () => call<Doc[]>("/documents");
export const reprocessDoc = (id: number) => call<Doc>(`/documents/${id}/reprocess`, { method: "POST" });
export const deleteDoc = (id: number) => call<void>(`/documents/${id}`, { method: "DELETE" });
export const uploadDoc = (file: File, chunkWords: number, chunkOverlap: number) => {
  const form = new FormData();
  form.append("file", file);
  form.append("chunkWords", String(chunkWords));
  form.append("chunkOverlap", String(chunkOverlap));
  return call<Doc>("/documents", { method: "POST", body: form });
};
export const askDocs = (question: string, documentIds: number[], topK: number, candidates: number, minScore: number | null, generate: boolean, model: string | null) =>
  call<Answer>("/ask", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ question, documentIds, topK, candidates, rerank: true, minScore, generate, model }),
  });
