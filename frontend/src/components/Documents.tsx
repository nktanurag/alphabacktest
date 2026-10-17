import { useEffect, useRef, useState } from "react";
import { AuthRequired } from "../api";
import { askDocs, deleteDoc, docqaConfig, listDocs, listModels, reprocessDoc, uploadDoc, type Answer, type Doc, type DocqaConfig, type ModelList } from "../docqaApi";
import { Button, inputCls } from "./ui";

const CANDIDATES = 30;
const snippet = (t: string) => (t.length > 170 ? `${t.slice(0, 170)}…` : t);
function Setting({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) {
  return (
    <label className="block min-w-0">
      <span className="block text-xs font-medium text-slate-400 mb-1">{label}</span>
      {children}
      <span className="block text-[11px] text-slate-600 mt-1">{hint}</span>
    </label>
  );
}

/** A heading that shows or hides its content. Stays accessible: a button with aria-expanded. */
function Collapsible({ title, summary, open, onToggle, children }: {
  title: string; summary: string; open: boolean; onToggle: () => void; children: React.ReactNode;
}) {
  return (
    <div>
      <button type="button" onClick={onToggle} aria-expanded={open}
        className="w-full flex items-center gap-2 text-left rounded-lg px-1 py-1 -mx-1 hover:bg-white/5">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
          className={`shrink-0 text-slate-500 transition-transform ${open ? "rotate-90" : ""}`} aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
        <span className="text-sm font-medium text-slate-300">{title}</span>
        <span className="text-xs text-slate-500 truncate">{summary}</span>
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  );
}

const mb = (n: number) => `${(n / (1024 * 1024)).toFixed(1)} MB`;

export default function Documents({ onAuthRequired }: { onAuthRequired: () => void }) {
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [deselected, setDeselected] = useState<Set<number>>(new Set());   // everything searchable is selected unless unticked here
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [question, setQuestion] = useState("");
  const [cfg, setCfg] = useState<DocqaConfig | null>(null);
  const [chunkWords, setChunkWords] = useState("300");
  const [chunkOverlap, setChunkOverlap] = useState("50");
  const [topK, setTopK] = useState("5");          // how many results to show after reranking
  const [minScore, setMinScore] = useState("");   // empty = no relevance cutoff; starts at the server default
  const [generate, setGenerate] = useState(false);   // ask Gemini for a cited answer (sends the question and passages to Google)
  const [models, setModels] = useState<ModelList | null>(null);   // answer models Google lists for the server's key
  const [model, setModel] = useState<string>(() => { try { return localStorage.getItem("docqaModel") ?? ""; } catch { return ""; } });
  const [asking, setAsking] = useState(false);
  const [result, setResult] = useState<{ q: string; a: Answer; topK: number } | null>(null);
  const [showResults, setShowResults] = useState(false);   // collapsed until the user opens it
  const fileInput = useRef<HTMLInputElement>(null);

  const fail = (e: unknown) => (e instanceof AuthRequired ? onAuthRequired() : setError((e as Error).message));
  const load = () => listDocs().then(setDocs).catch(fail);
  useEffect(() => { load(); }, []);
  useEffect(() => { docqaConfig().then((c) => {
      setCfg(c); setMinScore(c.minScore == null ? "" : String(c.minScore));
      setChunkWords(String(c.chunkWords)); setChunkOverlap(String(c.chunkOverlap)); setTopK(String(c.topK));
    }).catch(() => {}); }, []);
  // The model list needs the server's Gemini key; without it the dropdown stays hidden and the server default is used.
  useEffect(() => { if (generate && !models) listModels().then(setModels).catch(() => {}); }, [generate, models]);
  const chooseModel = (m: string) => { setModel(m); try { localStorage.setItem("docqaModel", m); } catch { /* private window */ } };
  const chosenModel = models && model && models.models.some((m) => m.id === model) ? model : "";   // "" = server default
  // Keep refreshing while any document is still being processed.
  useEffect(() => {
    if (!docs?.some((d) => d.status === "processing")) return;
    const t = setTimeout(load, 2000);
    return () => clearTimeout(t);
  }, [docs]);

  const size = Number(chunkWords), overlap = Number(chunkOverlap);
  const chunkProblem = !cfg ? null
    : !Number.isInteger(size) || size < cfg.minChunkWords || size > cfg.maxChunkWords ? `Chunk size must be ${cfg.minChunkWords} to ${cfg.maxChunkWords} words.`
    : !Number.isInteger(overlap) || overlap < 0 || overlap > Math.floor(size / 2) ? `Overlap must be 0 to ${Math.floor(size / 2)} words (half the chunk size).`
    : null;

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setError(null); setUploading(true);
    try { await uploadDoc(file, size, overlap); await load(); } catch (e) { fail(e); }
    setUploading(false);
    if (fileInput.current) fileInput.current.value = "";
  };

  const reprocess = async (id: number) => {
    setError(null);
    try { await reprocessDoc(id); await load(); } catch (e) { fail(e); }
  };

  const remove = async (id: number) => {
    setError(null);
    try {
      await deleteDoc(id);
      setDeselected((p) => { const n = new Set(p); n.delete(id); return n; });
      await load();
    } catch (e) { fail(e); }
  };

  const topKNumber = Number(topK);
  const topKProblem = cfg && (!Number.isInteger(topKNumber) || topKNumber < 1 || topKNumber > cfg.maxTopK)
    ? `Results must be a whole number from 1 to ${cfg.maxTopK}.` : null;

  const minScoreProblem = minScore.trim() !== "" && !Number.isFinite(Number(minScore))
    ? "Minimum relevance score must be a number such as -2.5 (use a dot), or empty for no cutoff." : null;

  const ask = async () => {
    const q = question.trim();
    if (!q || minScoreProblem || topKProblem || selectedIds.length === 0) return;
    setError(null); setAsking(true);
    try { setResult({ q, topK: topKNumber, a: await askDocs(q, selectedIds, topKNumber, Math.max(CANDIDATES, topKNumber), minScore.trim() === "" ? null : Number(minScore), generate, generate && chosenModel ? chosenModel : null) }); } catch (e) { fail(e); }
    setAsking(false);
  };

  const searchable = docs?.filter((d) => d.status === "ready" && !d.stale) ?? [];
  const selectedIds = searchable.filter((d) => !deselected.has(d.id)).map((d) => d.id);   // new, finished documents are included automatically
  const toggle = (id: number, on: boolean) => setDeselected((p) => { const n = new Set(p); on ? n.delete(id) : n.add(id); return n; });
  const allSelectRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (allSelectRef.current) allSelectRef.current.indeterminate = selectedIds.length > 0 && selectedIds.length < searchable.length; });

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 space-y-8">
      <header>
        <h1 className="text-xl font-semibold">Documents</h1>
        <p className="text-sm text-slate-500">Upload PDFs, then search them. You get the best-matching passages.</p>
      </header>

      {error && <div role="alert" className="rounded-xl border border-danger/25 bg-danger/5 px-5 py-3 text-sm text-danger">{error}</div>}

      <section aria-label="Settings" className="bg-surface border border-white/8 rounded-xl px-5 py-4 space-y-2">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Setting label="Chunk size (words)" hint="Next upload">
            <input className={inputCls} inputMode="numeric" value={chunkWords} onChange={(e) => setChunkWords(e.target.value)} aria-label="Chunk size in words" />
          </Setting>
          <Setting label="Overlap (words)" hint="Next upload">
            <input className={inputCls} inputMode="numeric" value={chunkOverlap} onChange={(e) => setChunkOverlap(e.target.value)} aria-label="Overlap in words" />
          </Setting>
          <Setting label="Results to show" hint="Next question">
            <input className={inputCls} inputMode="numeric" value={topK} onChange={(e) => setTopK(e.target.value)} aria-label="Number of results" />
          </Setting>
          <Setting label="Min relevance score" hint="Empty = no cutoff">
            <input className={inputCls} inputMode="decimal" placeholder="off" value={minScore} onChange={(e) => setMinScore(e.target.value)} aria-label="Minimum relevance score" />
          </Setting>
        </div>
        <p className="text-xs text-slate-500">
          Chunk size and overlap apply to the next upload; upload the same file again with new values to re-chunk it.
          Results to show and the minimum score apply to the next question; results scoring below the minimum are hidden.
        </p>
        <label className="flex items-start gap-2 text-xs text-slate-400 pt-1">
          <input type="checkbox" className="mt-0.5" checked={generate} onChange={(e) => setGenerate(e.target.checked)} />
          <span>
            Generate an answer with citations (Gemini). Sends your question and the top passages to Google; on the free tier Google may use them to improve its products.
          </span>
        </label>
        {generate && models && (
          <label className="flex items-center gap-2 text-xs text-slate-400 pl-6">
            Model
            <select className={`${inputCls} max-w-xs`} value={chosenModel} onChange={(e) => chooseModel(e.target.value)} aria-label="Answer model">
              <option value="">Server default ({models.default})</option>
              {models.models.map((m) => <option key={m.id} value={m.id}>{m.id}</option>)}
            </select>
          </label>
        )}
        {chunkProblem && <p role="alert" className="text-xs text-danger">{chunkProblem}</p>}
        {topKProblem && <p role="alert" className="text-xs text-danger">{topKProblem}</p>}
        {minScoreProblem && <p role="alert" className="text-xs text-danger">{minScoreProblem}</p>}
      </section>

      <section aria-label="Your documents" className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-300">Your documents</h2>
          <div>
            <input ref={fileInput} type="file" accept="application/pdf,.pdf" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
            <Button variant="primary" disabled={uploading || chunkProblem !== null} onClick={() => fileInput.current?.click()}>{uploading ? "Uploading…" : "+ Upload PDF"}</Button>
          </div>
        </div>
        {docs === null && !error && <p className="text-sm text-slate-500">Loading…</p>}
        {docs?.length === 0 && <p className="text-sm text-slate-500 py-6 text-center">No documents yet. Upload a PDF with selectable text (scans are not supported).</p>}
        <ul className="space-y-2">
          {docs?.map((d) => (
            <li key={d.id} className="bg-surface border border-white/8 rounded-xl px-4 py-3 flex items-center gap-3">
              <input type="checkbox" aria-label={`Search only ${d.filename}`} disabled={d.status !== "ready" || d.stale}
                checked={d.status === "ready" && !d.stale && !deselected.has(d.id)}
                onChange={(e) => toggle(d.id, e.target.checked)} />
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{d.filename}</div>
                <div className="text-xs text-slate-500">
                  {d.status === "ready" && `${d.pageCount} pages · ${d.chunkCount} passages · ${mb(d.sizeBytes)}`}
                  {d.status === "ready" && d.pdfTitle && ` · “${d.pdfTitle}”`}
                  {d.status === "ready" && d.pdfAuthor && ` · ${d.pdfAuthor}`}
                  {d.status === "ready" && d.pdfCreated && ` · ${d.pdfCreated}`}
                  {d.status === "processing" && "Processing…"}
                  {d.status === "failed" && <span className="text-danger">{d.error}</span>}
                </div>
                {d.status === "ready" && (
                  <div className="text-[11px] text-slate-600 mt-0.5 font-mono truncate">
                    {d.chunkWords}/{d.chunkOverlap} word chunks · {d.embeddingModel ?? "unknown embedding model"}
                  </div>
                )}
                {d.stale && (
                  <div role="status" className="text-xs text-warning mt-1">
                    Prepared with an older version of the processing, so it is skipped in searches until it is re-processed.
                  </div>
                )}
              </div>
              {(d.stale || d.status === "failed") && (
                <Button variant="ghost" aria-label={`${d.stale ? "Re-process" : "Retry"} ${d.filename}`} onClick={() => reprocess(d.id)}>
                  {d.stale ? "Re-process" : "Retry"}
                </Button>
              )}
              <Button variant="ghost" aria-label={`Delete ${d.filename}`} onClick={() => remove(d.id)}>Delete</Button>
            </li>
          ))}
        </ul>
        {searchable.length > 0 && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <label className="flex items-center gap-2">
              <input ref={allSelectRef} type="checkbox" checked={selectedIds.length === searchable.length}
                onChange={(e) => setDeselected(e.target.checked ? new Set() : new Set(searchable.map((d) => d.id)))} aria-label="Select all documents" />
              Select all
            </label>
            <span>· Searching {selectedIds.length} of {searchable.length} document{searchable.length === 1 ? "" : "s"}.</span>
            {selectedIds.length === 0 && <span role="status" className="text-warning">Select at least one document to ask a question.</span>}
          </div>
        )}
      </section>

      <section aria-label="Ask a question" className="space-y-3">
        <h2 className="text-sm font-medium text-slate-300">Ask</h2>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(); }}>
          <input className={`${inputCls} flex-1`} placeholder="What do you want to know?" value={question}
            onChange={(e) => setQuestion(e.target.value)} maxLength={2000} />
          <Button variant="primary" type="submit" disabled={asking || !question.trim() || selectedIds.length === 0 || topKProblem !== null || minScoreProblem !== null}>{asking ? "Searching…" : "Ask"}</Button>
        </form>
        {result?.a.answer && (
          <div className="bg-surface border border-primary/30 rounded-xl px-5 py-4">
            <h3 className="text-sm font-medium text-slate-300 mb-2">Answer</h3>
            <p className="text-sm text-slate-200 whitespace-pre-wrap">{result.a.answer}</p>
            <ul className="mt-3 space-y-0.5 text-xs text-slate-500">
              {result.a.chunks.map((c, i) => <li key={c.chunkId}>[{i + 1}] {c.filename}, page {c.page}{c.section ? ` · ${c.section}` : ""}</li>)}
            </ul>
            <p className="text-[11px] text-slate-600 mt-2">Generated from the passages below; check the citations, especially for numbers in tables.</p>
          </div>
        )}
        {result?.a.answerError && (
          <p role="alert" className="text-sm text-warning">Could not generate an answer: {result.a.answerError} The passages are below.</p>
        )}
        {result && (
          <div className="bg-surface border border-white/8 rounded-xl px-5 py-4">
            <Collapsible title={`Results for “${result.q}”`}
              summary={`${result.a.candidates.length} candidates → ${result.a.chunks.length} result${result.a.chunks.length === 1 ? "" : "s"}`}
              open={showResults} onToggle={() => setShowResults((v) => !v)}>
              <div className="space-y-4 pt-2">
                {result.a.candidates.length === 0 && <p className="text-sm text-slate-500">No passages found.</p>}
                {result.a.candidates.length > 0 && result.a.chunks.length === 0 && (
                  <p role="status" className="text-sm text-warning">
                    No relevant passages found in your documents: the top {result.a.droppedBelowCutoff} all scored below {result.a.minScore}.
                  </p>
                )}
                <div className="grid lg:grid-cols-2 gap-6 items-start">
                  <div>
                    <h3 className="text-sm font-medium text-slate-300">Before reranking</h3>
                    <p className="text-xs text-slate-500 mb-2">{result.a.candidates.length} candidates: vector (meaning) and keyword results merged. Highlighted ones made the final {result.topK}.</p>
                    <ol className="space-y-1.5">
                      {result.a.candidates.map((c) => {
                        const kept = result.a.chunks.some((k) => k.chunkId === c.chunkId);
                        return (
                          <li key={c.chunkId} className={`rounded-lg border px-3 py-2 ${kept ? "border-primary/40 bg-primary/5" : "border-white/8 bg-field"}`}>
                            <div className="flex items-center justify-between text-xs text-slate-500">
                              <span>#{c.rank} · {c.filename} · p.{c.page}</span>
                              <span className="font-mono" title="vector rank and similarity · keyword rank">
                                {c.vectorRank ? `vec #${c.vectorRank}` : "vec –"} {c.vectorScore.toFixed(3)} · {c.keywordRank ? `kw #${c.keywordRank}` : "kw –"}
                              </span>
                            </div>
                            {c.section && <p className="text-[11px] text-slate-500 mt-0.5 truncate">{c.section}</p>}
                            <p className="text-xs text-slate-400 mt-1">{snippet(c.text)}</p>
                          </li>
                        );
                      })}
                    </ol>
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-slate-300">After reranking</h3>
                    <p className="text-xs text-slate-500 mb-2">
                      The best {result.topK}, scored by a model that reads the question and passage together.
                      {result.a.droppedBelowCutoff > 0 && result.a.chunks.length > 0 && ` ${result.a.droppedBelowCutoff} hidden for scoring below ${result.a.minScore}.`}
                    </p>
                    <ol className="space-y-2">
                      {result.a.chunks.map((c, i) => {
                        const moved = c.rank - (c.rerankRank ?? c.rank);
                        return (
                          <li key={c.chunkId} className="bg-field border border-white/8 rounded-xl px-4 py-3">
                            <div className="flex items-center justify-between text-xs text-slate-500 mb-1.5">
                              <span>[{i + 1}] #{c.rerankRank} · {c.filename} · page {c.page}</span>
                              <span className="font-mono">
                                <span className={moved > 0 ? "text-success" : moved < 0 ? "text-danger" : ""}>
                                  {moved > 0 ? `↑${moved}` : moved < 0 ? `↓${-moved}` : "="}
                                </span>{" "}was #{c.rank} · score {c.rerankScore?.toFixed(2)}
                              </span>
                            </div>
                            {c.section && <p className="text-xs text-slate-400 mb-1.5">{c.section}</p>}
                            <p className="text-sm text-slate-300 whitespace-pre-wrap">{c.text}</p>
                          </li>
                        );
                      })}
                    </ol>
                  </div>
                </div>
              </div>
            </Collapsible>
          </div>
        )}
      </section>
    </div>
  );
}
