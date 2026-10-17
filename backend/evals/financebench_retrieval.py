"""Retrieval evaluation of Document Q&A on FinanceBench (see docs/DOCQA_EVAL.md).

Run from backend/, with the data in a folder OUTSIDE the repository (never commit it):

    python -m evals.financebench_retrieval --data-dir /path/to/financebench

The data folder holds `questions.jsonl` (FinanceBench open-source sample) and `pdfs/<doc_name>.pdf`.
It uses its own database (default postgresql://localhost/docqa_eval) and a dummy user, never your real documents.
No LLM and no network are used. Documents already ingested with the same settings are reused.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path


def _args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", required=True, help="folder with questions.jsonl and pdfs/")
    p.add_argument("--db", default="postgresql://localhost/docqa_eval", help="evaluation database (never the real one)")
    p.add_argument("--docs-file", help="text file with one doc_name per line (default: <data-dir>/top12.txt)")
    p.add_argument("--only", help="comma-separated doc_names, overrides --docs-file (for a quick smoke test)")
    p.add_argument("--chunk-words", type=int, default=300)
    p.add_argument("--overlap", type=int, default=50)
    p.add_argument("--pool", type=int, default=30, help="candidates fetched per search (the system default is 30)")
    p.add_argument("--extractor", choices=("pypdf", "plumber"), default="pypdf",
                   help="page text: the app's pypdf, or the experimental table-grid-preserving pdfplumber one")
    p.add_argument("--bm25-header", action="store_true", help="keyword search also sees each chunk's title and section")
    p.add_argument("--name-boost", action="store_true", help="also search inside documents whose name the question mentions")
    p.add_argument("--oracle", action="store_true",
                   help="ceiling test: search with the first evidence text (first 300 words) instead of the question")
    p.add_argument("--expand", action="store_true",
                   help="search with the question plus a Gemini-written description of the page that would answer it "
                        "(needs GEMINI_API_KEY; sends the benchmark questions to Google; cached in <data-dir>/<--expansions-file>)")
    p.add_argument("--expansions-file", default="expansions_gemini.json",
                   help="cache file (in the data folder) for --expand; one file per source of descriptions")
    p.add_argument("--rerank-expanded", action="store_true",
                   help="with --expand: the reranker also scores against the expanded text (default: the original question)")
    p.add_argument("--tag", default="", help="suffix for the results folder")
    p.add_argument("--no-rerank", action="store_true", help="skip the reranked configurations (fast)")
    p.add_argument("--out", help="results folder (default: <data-dir>/results/c<chunk>_o<overlap>)")
    return p.parse_args()


args = _args()
if args.db.rstrip("/").rsplit("/", 1)[-1] in ("docqa", "alphabacktest"):
    sys.exit("Refusing to run against that database: use a separate evaluation database (createdb docqa_eval).")
DATA = Path(args.data_dir).resolve()
os.environ["DOCQA_DATABASE_URL"] = args.db            # must be set before docqa is imported
os.environ["DOCQA_STORAGE_DIR"] = str(DATA / "storage")

import hashlib  # noqa: E402

from sqlalchemy import select  # noqa: E402

from docqa import bm25, chunking, clean, config, db, extract, pipeline, providers  # noqa: E402
from docqa.models import Chunk, Document  # noqa: E402
from docqa.storage import document_prefix, get_storage  # noqa: E402

# One dummy user per chunk size and extractor, so the same file can exist in several variants side by side.
EVAL_USER = 1_000_000 + args.chunk_words + (10_000 if args.extractor == "plumber" else 0)
KS = (1, 3, 5, 10, 30)
LOCATE_MIN = 0.4                              # share of the evidence's word triples that must appear on a page


if args.extractor == "plumber":
    from evals import plumber_extract

    _original_extract = extract.extract_pdf

    def _extract_with_grid(data: bytes):
        base = _original_extract(data)   # title, author, bookmarks, and the same rejections as the app
        pages = plumber_extract.extract_pages(data)
        return extract.Extracted(clean.clean_pages(pages), base.sections, base.title, base.author, base.created)

    extract.extract_pdf = _extract_with_grid


EXPAND_SYSTEM = (
    "You help a search engine find the page of a long document that answers a question. Write what that page would "
    "contain, in the document's own wording: the section or statement titles, the names of the line items, figures or "
    "terms it would show, and the standard terms for the concepts in the question. Output one short paragraph of plain "
    "text, with no preamble. Do not answer the question and do not guess numbers.")


def expansions(questions: list[dict]) -> dict[str, str]:
    """question id -> Gemini's description of the answering page, cached on disk so a rerun costs nothing."""
    path = DATA / args.expansions_file
    cache = json.loads(path.read_text()) if path.exists() else {}
    todo = [q for q in questions if q["financebench_id"] not in cache]
    if todo and not config.gemini_api_key():
        sys.exit("--expand needs GEMINI_API_KEY in this terminal (export it, then run again).")
    for n, q in enumerate(todo, start=1):
        cache[q["financebench_id"]] = providers.generate(EXPAND_SYSTEM, f"Question: {q['question']}").strip()
        path.write_text(json.dumps(cache, indent=1))
        print(f"  expanded {n}/{len(todo)}", flush=True)
        time.sleep(6)   # stay under the free tier's requests per minute
    return cache


# ---------------------------------------------------------------- data
def load_questions(doc_names: list[str]) -> list[dict]:
    rows = [json.loads(line) for line in (DATA / "questions.jsonl").read_text().splitlines() if line.strip()]
    return [r for r in rows if r["doc_name"] in doc_names]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _triples(tokens: list[str]) -> set[tuple[str, str, str]]:
    return {tuple(tokens[i:i + 3]) for i in range(len(tokens) - 2)}


def is_table_like(evidence_text: str) -> bool:
    toks = _tokens(evidence_text)
    return bool(toks) and sum(t.isdigit() for t in toks) / len(toks) >= 0.4


# ---------------------------------------------------------------- ingest
def ensure_documents(s, doc_names: list[str]) -> dict[str, int]:
    """doc_name -> document id, ingesting what is missing (slow: embedding runs on the CPU)."""
    ids = {}
    for name in doc_names:
        fname = f"{name}.pdf"
        data = (DATA / "pdfs" / fname).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        same = s.scalar(select(Document).where(Document.user_id == EVAL_USER, Document.filename == fname))
        if (same and same.status == "ready" and same.embedding_model == config.current_embedding_model()
                and (same.chunk_words, same.chunk_overlap) == (args.chunk_words, args.overlap)):
            ids[name] = same.id
            continue
        if same:
            s.delete(same)
            s.commit()
        doc = Document(user_id=EVAL_USER, filename=fname, file_type="pdf", size_bytes=len(data), file_hash=digest,
                       chunk_words=args.chunk_words, chunk_overlap=args.overlap)
        s.add(doc)
        s.flush()
        doc.storage_key = f"{document_prefix(EVAL_USER, doc.id)}/original.pdf"
        get_storage().put(doc.storage_key, data)
        s.commit()
        t = time.time()
        print(f"ingesting {fname} ...", flush=True)
        pipeline.ingest(doc.id)
        s.expire_all()
        doc = s.get(Document, doc.id)
        print(f"  {doc.status}: {doc.page_count} pages, {doc.chunk_count} chunks in {time.time() - t:.0f}s"
              + (f" ({doc.error})" if doc.error else ""), flush=True)
        if doc.status != "ready":
            sys.exit(f"{fname} failed to ingest: {doc.error}")
        ids[name] = doc.id
    return ids


# ---------------------------------------------------------------- locating the evidence
def locate_evidence(s, ids: dict[str, int], questions: list[dict]):
    """For each question, the (doc_name, page) pairs that hold its evidence, found by matching the evidence text
    against our own extracted pages (the dataset's page numbering may be 0- or 1-based, so it is only reported)."""
    page_triples: dict[str, dict[int, set]] = {}
    for name, did in ids.items():
        by_page = defaultdict(list)
        for page, text in s.execute(select(Chunk.page, Chunk.text).where(Chunk.document_id == did).order_by(Chunk.position)):
            by_page[page].append(text)
        page_triples[name] = {p: _triples(_tokens(" ".join(t))) for p, t in by_page.items()}
    offsets, located, total = Counter(), 0, 0
    for q in questions:
        q["relevant"] = set()
        q["table_like"] = False
        flags = []
        for ev in q["evidence"]:
            total += 1
            etrip = _triples(_tokens(ev["evidence_text"]))
            flags.append(is_table_like(ev["evidence_text"]))
            if not etrip:
                continue
            scores = {p: len(etrip & tr) / len(etrip) for p, tr in page_triples[q["doc_name"]].items()}
            best = max(scores.values(), default=0)
            if best >= LOCATE_MIN:
                located += 1
                pages = [p for p, v in scores.items() if v >= best - 0.05]
                q["relevant"] |= {(q["doc_name"], p) for p in pages}
                labelled = ev.get("evidence_page_num")
                if labelled is not None and len(pages) == 1:
                    offsets[pages[0] - labelled] += 1
        q["table_like"] = bool(flags) and sum(flags) * 2 > len(flags)
    return located, total, offsets


# ---------------------------------------------------------------- search
def run(s, ids: dict[str, int], questions: list[dict], pool: int, rerank: bool, expanded: dict[str, str] | None = None):
    names = {v: k for k, v in ids.items()}
    chunk_page = {cid: (names[did], page) for cid, did, page in s.execute(
        select(Chunk.id, Chunk.document_id, Chunk.page).where(Chunk.document_id.in_(list(ids.values()))))}
    texts: dict[tuple, list] = {}

    def scope_rows(doc_ids: tuple[int, ...]):
        if doc_ids not in texts:
            rows = s.execute(select(Chunk.id, Chunk.text, Chunk.section, Document.pdf_title, Document.filename)
                             .join(Document, Document.id == Chunk.document_id).where(Chunk.document_id.in_(doc_ids))).all()
            texts[doc_ids] = [(cid, chunking.with_context(pipeline._title(t, f), sec, text) if args.bm25_header else text)
                              for cid, text, sec, t, f in rows]
        return texts[doc_ids]

    def pages(hits):
        return [chunk_page[h.chunk_id] for h in hits]

    results = []   # (question, scope, config, first_rank or None, top5 pages)
    all_ids = tuple(sorted(ids.values()))
    for n, q in enumerate(questions, start=1):
        if not q["relevant"]:
            continue
        for scope, doc_ids in (("single", (ids[q["doc_name"]],)), ("shared", all_ids)):
            question = " ".join(q["evidence"][0]["evidence_text"].split()[:300]) if args.oracle else q["question"]
            search = f"{question}\n{expanded[q['financebench_id']]}" if expanded else question   # what is searched
            flags = dict(bm25_header=args.bm25_header, name_boost=args.name_boost)
            vector = pipeline.retrieve(s, EVAL_USER, search, list(doc_ids), pool, hybrid=False, **flags)
            hybrid = pipeline.retrieve(s, EVAL_USER, search, list(doc_ids), pool, hybrid=True, **flags)
            keyword = [chunk_page[c] for c, _ in bm25.rank(search, scope_rows(doc_ids), pool)]
            lists = {"vector": pages(vector), "keyword": keyword, "hybrid": pages(hybrid)}
            if rerank:
                rq = search if args.rerank_expanded else question
                lists["vector+rerank"] = pages(pipeline.rerank(rq, vector))
                lists["hybrid+rerank"] = pages(pipeline.rerank(rq, hybrid))
            for cfg, ranked in lists.items():
                first = next((i for i, p in enumerate(ranked, start=1) if p in q["relevant"]), None)
                results.append((q, scope, cfg, first, ranked[:5]))
        if n % 10 == 0:
            print(f"  asked {n}/{len(questions)} questions", flush=True)
    return results


# ---------------------------------------------------------------- reporting
def metrics(rows):
    """rows: list of first-rank values (None = not found). Recall@k and MRR."""
    n = len(rows)
    if not n:
        return None
    rec = {k: sum(1 for r in rows if r is not None and r <= k) / n for k in KS}
    mrr = sum(1 / r for r in rows if r is not None) / n
    return n, rec, mrr


def table(results, key=lambda q: None):
    configs = list(dict.fromkeys(c for _, _, c, _, _ in results))
    out = []
    groups = sorted({key(q) for q, *_ in results}, key=str)
    for scope in ("single", "shared"):
        for g in groups:
            lines = []
            for cfg in configs:
                rows = [first for q, sc, c, first, _ in results if sc == scope and c == cfg and key(q) == g]
                m = metrics(rows)
                if m:
                    n, rec, mrr = m
                    lines.append(f"| {cfg} | " + " | ".join(f"{rec[k]:.2f}" for k in KS) + f" | {mrr:.3f} | {n} |")
            if lines:
                title = f"**{scope}**" + (f", {g}" if g is not None else "")
                out.append(f"\n{title}\n\n| config | R@1 | R@3 | R@5 | R@10 | R@30 | MRR | n |\n|---|---|---|---|---|---|---|---|\n"
                           + "\n".join(lines))
    return "\n".join(out)


def main():
    t0 = time.time()
    doc_names = ([d.strip() for d in args.only.split(",")] if args.only
                 else (Path(args.docs_file) if args.docs_file else DATA / "top12.txt").read_text().split())
    db.init_db()
    with db.session() as s:
        questions = load_questions(doc_names)
        print(f"{len(doc_names)} documents, {len(questions)} questions, chunks {args.chunk_words}/{args.overlap}", flush=True)
        ids = ensure_documents(s, doc_names)
        located, total, offsets = locate_evidence(s, ids, questions)
        usable = [q for q in questions if q["relevant"]]
        print(f"evidence located on a page: {located}/{total}; questions usable: {len(usable)}/{len(questions)}; "
              f"labelled-vs-found page offsets (found - labelled): {dict(offsets)}", flush=True)
        expanded = expansions(usable) if args.expand else None
        results = run(s, ids, usable, args.pool, not args.no_rerank, expanded)

    out = Path(args.out) if args.out else DATA / "results" / (
        f"c{args.chunk_words}_o{args.overlap}" + ("_plumber" if args.extractor == "plumber" else "") + args.tag)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "per_question.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "doc", "type", "table_like", "scope", "config", "first_hit_rank", "expected_pages", "top5_pages", "question"])
        for q, scope, cfg, first, top5 in results:
            w.writerow([q["financebench_id"], q["doc_name"], q["question_type"], q["table_like"], scope, cfg, first or "",
                        ";".join(f"{d}:{p}" for d, p in sorted(q["relevant"])),
                        ";".join(f"{d}:{p}" for d, p in top5), q["question"]])
    report = [f"# FinanceBench retrieval, chunks {args.chunk_words}/{args.overlap}, pool {args.pool}, extractor {args.extractor}, oracle {args.oracle}, expand {args.expand}, rerank_expanded {args.rerank_expanded}, bm25_header {args.bm25_header}, name_boost {args.name_boost}",
              f"\n{len(doc_names)} documents, {len(usable)} usable questions of {len(questions)}; "
              f"evidence located {located}/{total}; page offsets (found - labelled) {dict(offsets)}.",
              "\n## All questions\n", table(results),
              "\n## By question type\n", table(results, key=lambda q: q["question_type"]),
              "\n## Table-like evidence vs text\n", table(results, key=lambda q: "table" if q["table_like"] else "text")]
    (out / "summary.md").write_text("\n".join(report) + "\n")
    print("\n".join(report))
    print(f"\nwritten to {out} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
