# Document Q&A

Upload PDFs (annual reports are the target), ask a question, and get the best-matching passages ranked before and after reranking, plus (optionally) a Gemini-written answer that cites them. Search, embedding and reranking run locally; no API key is needed except for generated answers.

This is the one document for the feature: how to set it up and use it (Part 1), how it works (Part 2), and where it stands and what comes next (Part 3). The plan for measuring search quality is in [DOCQA_EVAL.md](DOCQA_EVAL.md).

**Contents.** Part 1: [What it is](#what-it-is) · [Setup](#setup) · [The Documents page](#the-documents-page) · [Settings](#settings) · [Things to know](#things-to-know). Part 2: [Architecture](#architecture) · [Technology](#technology) · [Data model](#data-model) · [Ingestion](#flow-1-ingestion-upload) · [Asking](#flow-2-asking) · [API reference](#api-reference) · [Security and privacy](#security-and-privacy) · [Errors](#errors-and-edge-cases) · [Testing](#testing) · [Deploying](#deploying). Part 3: [Status](#status) · [Known limitations](#known-limitations) · [Findings](#findings-from-real-documents) · [Next steps](#next-steps) · [Decisions](#decisions-and-why).

---

# Part 1: Using it

## What it is

A user uploads PDF documents and asks a question. The system returns the passages most likely to contain the answer, ranked best first. It shows the ranking **before** and **after** a reranking step so the effect of reranking can be seen. An optional Gemini-written answer with citations is available through a checkbox in the UI (off by default).

It is a **separate system** that happens to live in the same repository, server process and web UI as the AlphaBacktest backtester:

| | Shared with the backtester | Separate |
|---|---|---|
| Web UI | one app, one nav bar (a "Documents" tab) | its own page and API client |
| Server | same FastAPI process and the same container | its own router (`/api/docqa/*`) |
| Identity | the signed-in user's id (Google sign-in, or the shared local user when login is off) | |
| Database | | its own Postgres database (`docqa`), its own engine and tables |
| Code | | its own package, `backend/docqa/` |
| Config | | its own environment variables (`DOCQA_*`, `GEMINI_API_KEY`) |

It is **off by default**. Without `DOCQA_DATABASE_URL`, the Documents tab is hidden and `/api/docqa/*` answers 503. The backtester and the current Render deployment are unaffected.

### In scope (v1)

- Upload PDFs that contain real, selectable text.
- Search one, several or all of the user's documents.
- Return top-ranked passages with file name, page and scores, before and after reranking.
- Keep every user's documents private to them.

### Out of scope (v1)

Scanned PDFs and OCR, Word and plain-text files, conversation history, sharing documents between users, tables and charts as structured data, and production deployment.

## Setup

### 1. Postgres 17 or 18 with pgvector

pgvector must be installed in the database. Homebrew's pgvector supports Postgres 17 and 18 (not 15 or 16).

```bash
# macOS (Homebrew)
brew install postgresql@18 pgvector
brew services start postgresql@18
/opt/homebrew/opt/postgresql@18/bin/createdb docqa
```

Or with Docker (not tested on the author's machine, which has no Docker): any image that includes pgvector works, for example

```bash
docker run -d --name docqa-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 pgvector/pgvector:pg17
docker exec docqa-pg createdb -U postgres docqa
# then use: DOCQA_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/docqa
```

On Linux or Windows, install Postgres 17 or 18 and the pgvector package for it, then `createdb docqa`. The app runs `CREATE EXTENSION vector` and creates its tables itself at startup, so the database user must be allowed to create the extension (a superuser or the database owner on a normal local install).

### 2. Python packages

The backend `requirements.txt` already includes everything (`fastembed`, `pypdf`, `pgvector`, `psycopg`). Install it as in the README. If your virtual environment has no `pip` (a `uv` venv), use `uv pip install --python .venv/bin/python -r requirements.txt`.

### 3. Optional: a Gemini API key (only for generated answers)

Search, embedding and reranking need **no key**. A key is needed only to tick **Generate an answer** (or to use `DOCQA_EMBEDDING_PROVIDER=gemini`).

1. Create a key at https://aistudio.google.com/apikey (free tier; sign in with a Google account).
2. Set `GEMINI_API_KEY` in the terminal that starts the backend (below). Never put the key in the repository.
3. If answers fail with a 404 ("model is no longer available"), Google has retired the default model. Pick another in the **Model** dropdown (it lists what your key can use), or set `DOCQA_GENERATION_MODEL` for everyone. The default in the code is `gemini-3.8-flash`. A model can appear in the list yet have no free-tier quota, which shows as a quota error.

**Privacy of the free tier:** when you tick **Generate an answer**, your question and the top passages are sent to Google, and on the free tier Google may use them to improve its products. Leave the box unticked for sensitive documents. Nothing is sent otherwise.

### 4. Start the backend with the settings in the same terminal

The variables must be set **in the same terminal, before** the server starts. Setting them afterwards has no effect. Run from the `backend/` folder:

```bash
export DOCQA_DATABASE_URL=postgresql://localhost/docqa
export GEMINI_API_KEY=your-key-here            # optional, see above
uvicorn alphabacktest.api:app --reload --port 8080
```

Check `curl localhost:8080/api/docqa/config`: it must show `"enabled": true`. Then start the frontend (`npm run dev` in `frontend/`) and open the **Documents** tab. If you turned on Google sign-in, the tab asks you to sign in first.

**Model cache.** The embedding model (about 500 MB) and the reranker (about 150 MB) download on first use into `.model_cache/` in the folder where you start the server (so `backend/.model_cache/`; it is git-ignored). Set `DOCQA_MODEL_CACHE_DIR` to keep them elsewhere, for example one shared folder for several checkouts. The first upload or question after each server start also waits about 20 seconds while the models load.

### 5. Try it

1. Upload a PDF that has selectable text (not a scan). The status changes from "Processing" to "ready"; a long report takes several minutes.
2. Ask a question. Open the results card to see the ranking before and after reranking.
3. Optionally tick **Generate an answer** (needs the key) to get an answer with `[1]`, `[2]` citations.

Troubleshooting:

| Symptom | Fix |
|---|---|
| No **Documents** tab | `DOCQA_DATABASE_URL` was not set in the terminal that started the server, or the database is unreachable. Check `/api/docqa/config` |
| `extension "vector" is not available` | pgvector is not installed for that Postgres version (use 17 or 18) |
| Document stuck on "Processing" | The server restarted during processing. Delete the document and upload again (Re-process refuses a document that is still marked processing) |
| "Prepared with an older version of the processing" (stale) | Click **Re-process**; it rebuilds the document from the stored PDF. Stale documents are skipped in searches until then |
| Answer fails with 404 | The Gemini model name was retired; pick another in the Model dropdown or set `DOCQA_GENERATION_MODEL` (above) |
| "Could not reach the model service" | No route to Google (network, VPN or proxy), or a slow reply; the server log has the reason (`Gemini request failed`) |
| "GEMINI_API_KEY is not set on the server" | Set it in the terminal that starts the backend and restart |

## The Documents page

The **Documents** page, top to bottom:

1. **Settings row** (one row of four boxes, two by two on a phone): **Chunk size (words)** and **Overlap (words)**, which apply to the next upload, and **Results to show** (1 to 20, default 5) and **Min relevance score** (default -2.5, empty means no cutoff), which apply to the next question. Below the boxes: the **Generate an answer** checkbox (off by default, with a privacy note) and, when it is ticked, a **Model** dropdown listing the Gemini models your key can use. Invalid values show an error and disable Upload or Ask.
2. **Your documents:** upload button (PDF only), a list with status (`Processing…`, page and passage counts, the PDF's title and author, the chunk settings and embedding model, or the failure reason or a stale warning with a **Re-process** button, a **Retry** button on failed ones), a checkbox on each ready document (all ticked by default, after every refresh; a document that finishes later is included automatically, because the page remembers what you un-ticked, not what you ticked), a "Select all" box with "Searching N of M documents", and delete. Ask is disabled while none is ticked. The list refreshes itself every two seconds while anything is processing.
3. **Ask:** a question box. With **Generate an answer** ticked, the answer appears in a card above the results with `[1]`, `[2]` citations and its source list (the reranked items are labelled `[1]`, `[2]` to match), or a warning if generation failed. Then **one collapsible results card**. It starts **collapsed**, showing only "Results for "<question>"" and a summary such as "7 candidates → 5 results". Opened, it shows two columns:
   - **Before reranking:** all 30 candidates in merged order (vector and keyword results combined), with rank, file, page, `vec #n` (vector rank) and similarity, `kw #n` (keyword rank), section and a short snippet; a dash means that search did not return it. The ones that made the final list are highlighted.
   - **After reranking:** the final results in full text, each showing its new rank, how far it moved (`↑4`, `↓2` or `=`), its old rank, and its reranker score. This is the list sent, with the question, to Gemini when **Generate an answer** is ticked.

If login is on and the user is signed out, the tab opens the same sign-in dialog as saved strategies. A `401` mid-session sends the user back to sign in.

## Settings

Set these in the terminal that starts the backend, before it starts.

| Variable | Default | Meaning |
|---|---|---|
| `DOCQA_DATABASE_URL` | unset (feature off) | Postgres URL with pgvector, for example `postgresql://localhost/docqa` |
| `GEMINI_API_KEY` | unset | Only for generated answers or `DOCQA_EMBEDDING_PROVIDER=gemini`. Issued at https://aistudio.google.com/apikey |
| `DOCQA_GENERATION_MODEL` | `gemini-3.8-flash` | Default model for answers; the Model dropdown can override it per question |
| `DOCQA_MIN_RERANK_SCORE` | `-2.5` | Default relevance cutoff; a number, or `off` |
| `DOCQA_STORAGE_DIR` | `./docqa_files` | Where original PDFs are kept |
| `DOCQA_MODEL_CACHE_DIR` | `./.model_cache` | Where the downloaded local models are kept (`FASTEMBED_CACHE_PATH` is honoured if this is unset) |
| `DOCQA_EMBEDDING_PROVIDER` | `local` | `local` (fastembed, no key) or `gemini` |
| `DOCQA_LOCAL_EMBEDDING_MODEL` | `jinaai/jina-embeddings-v2-base-en` | Must output 768 numbers (the column size). Changing it means re-uploading every document |
| `DOCQA_RERANK_MODEL` | `jinaai/jina-reranker-v1-turbo-en` | Any cross-encoder fastembed supports |
| `DOCQA_EMBEDDING_MODEL` | `gemini-embedding-001` | Only with the `gemini` embedding provider |

Fixed in `config.py`: 20 MB per file, 600 pages, 20 documents per user, default 300-word chunks with 50-word overlap (each upload may choose 100 to 800 and 0 to half the size), 768 embedding dimensions, default 5 results (the page may choose 1 to 20), 30 candidates. **Changing the chunk sizes, the embedding provider or the embedding model only affects documents uploaded afterwards, and vectors from different models cannot be compared, so re-process every document after such a change (new chunk settings only take effect through a fresh upload of the file).**

## Things to know

- **Speed.** Embedding runs on your CPU: roughly a third of a second per chunk, so a 600-page PDF (roughly 1,000 chunks) takes about 4 to 5 minutes. The first upload or question after each server start also waits about 20 seconds while the models load.
- **Privacy.** With the default local models, document text never leaves your machine. Text goes to Google only if you tick **Generate an answer** (the question and the final passages) or set `DOCQA_EMBEDDING_PROVIDER=gemini`; on the free tier Google may use it to improve its products. See [Security and privacy](#security-and-privacy).
- **Scanned PDFs are rejected** (no OCR), and Word and text files are not supported yet; only `extract.py` needs to change to add them.
- **Not deployed.** It needs Postgres with pgvector, persistent file storage and enough memory for two local models; see [Deploying](#deploying).

---

# Part 2: How it works

## Architecture

```mermaid
flowchart LR
  subgraph Browser
    UI["Documents page (React)"]
  end
  subgraph Server["FastAPI process"]
    API["/api/docqa router"]
    BG["Background ingest job"]
    RR["Reranker (fastembed, local ONNX)"]
  end
  FS[("File storage<br/>docqa_files/")]
  PG[("Postgres + pgvector<br/>documents, chunks")]
  EMB["Embedding model<br/>(local, fastembed)"]
  GEM["Gemini API<br/>(optional answers only)"]

  UI -->|"upload PDF"| API
  API -->|"save original"| FS
  API -->|"metadata row"| PG
  API -->|"schedule"| BG
  BG -->|"read PDF"| FS
  BG -->|"embed chunks"| EMB
  BG -->|"save chunks + vectors"| PG
  UI -->|"ask"| API
  API -->|"embed question"| EMB
  API -->|"nearest 30 chunks + text for keyword (BM25) search"| PG
  API -->|"score 30 merged candidates"| RR
  API -->|"candidates + top N"| UI
```

### Components

| Module (`backend/docqa/`) | Responsibility |
|---|---|
| `api.py` | HTTP endpoints, request validation, error mapping, per-user scoping |
| `pipeline.py` | The two flows: `ingest` (background) and `retrieve` + `rerank` (+ optional `answer`) |
| `extract.py` | PDF to text per page; rejects password-protected, oversized, unreadable and scanned files |
| `chunking.py` | Page text into overlapping word windows |
| `providers.py` | Calls to Gemini: `embed()` and `generate()`, with retry and friendly errors |
| `bm25.py` | Keyword (BM25) ranking over a user's chunks, merged with the vector results |
| `docmatch.py` | Finds which documents a question names (company, report, year) from titles and file names |
| `rerank.py` | Local cross-encoder reranking, lazily loaded |
| `models.py` | SQLAlchemy tables `documents` and `chunks` |
| `db.py` | Own engine and session, `init_db()` (creates the `vector` extension and tables) |
| `storage.py` | Reading and writing original files; the only code that touches the file system |
| `config.py` | Limits, defaults, and environment variables |

Frontend: `frontend/src/components/Documents.tsx` (the page) and `frontend/src/docqaApi.ts` (the API client). `App.tsx` adds the nav tab, shown only when `/api/docqa/config` says the feature is enabled.

## Technology

| Layer | Choice | Version here | Why |
|---|---|---|---|
| API | FastAPI, Uvicorn | 0.143, 0.54 | Already used by the app; background tasks and file uploads built in |
| ORM and DB driver | SQLAlchemy, psycopg 3 | 2.1, 3.3 | Same stack as the rest of the app |
| Vector store | PostgreSQL 18 with **pgvector** | pgvector 0.8.7, Python client 0.5 | One database for metadata and vectors; filtering by user is plain SQL; no extra service |
| PDF text | pypdf | 6.21 | Pure Python, page-level text, no system dependencies |
| Embeddings | **fastembed** with `jinaai/jina-embeddings-v2-base-en` (768 dimensions, 8,000-token input) on ONNX Runtime; Gemini `gemini-embedding-001` is a config option | fastembed 0.9 | Free, local, no quota and no data leaves the machine; the long input means chunks are never cut off |
| Reranking | **fastembed** cross-encoder `jinaai/jina-reranker-v1-turbo-en` on ONNX Runtime | fastembed 0.9, onnxruntime 1.31 | Free, local, no API key, 8,000-token input so 500-word chunks are not cut off |
| Answers (optional) | Gemini `gemini-3.8-flash` | free tier | Only used when `generate` is true; the only thing that needs `GEMINI_API_KEY` by default |
| File storage | Local disk behind `storage.py` | | Simplest start; shaped like an S3 path so a bucket can replace it |
| Frontend | React 19, TypeScript, Vite 6, Tailwind 4 | | Same as the rest of the app |
| Tests | pytest, FastAPI TestClient, reportlab (to build test PDFs) | | |

PostgreSQL 15 cannot be used: Homebrew's pgvector is built only for versions 17 and 18.

## Data model

```mermaid
erDiagram
  DOCUMENTS ||--o{ CHUNKS : has
  DOCUMENTS {
    int id PK
    int user_id "owner, from the main app"
    string filename
    string file_type "pdf"
    int size_bytes
    int page_count
    int chunk_count
    string status "processing | ready | failed"
    text error "why it failed"
    string storage_key "path of the original file"
    string file_hash "sha256; stops duplicate uploads"
    string embedding_model "model that made the vectors"
    int chunk_words "chunk size used"
    int chunk_overlap "overlap used"
    string pdf_title "from the PDF's own metadata"
    string pdf_author
    string pdf_created
    timestamptz created_at
  }
  CHUNKS {
    int id PK
    int document_id FK "cascade delete"
    int user_id "repeated so every search filters by owner"
    int page "1-based"
    int position "order inside the document"
    string section "heading path from the PDF bookmarks"
    text text
    vector_768 embedding
  }
```

- `user_id` has **no foreign key** to the main app's users table, because the systems are separate. It is simply the number.
- `chunks.user_id` duplicates the owner on purpose, so the search query filters by owner without a join.
- There is **no vector index**. A search is an exact scan of the user's chunks. That is correct and fast at thousands of chunks. Add an HNSW index (`vector_cosine_ops`) when it gets slow. Caution: with an approximate index plus a user filter, a search can return fewer results than asked, so test that when adding it.
- Tables are created on startup (`create_all`), and columns added later are added to existing tables with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (the list is in `db.py`). There is no full migration tool; renaming or removing columns would need one, such as Alembic.
- `(user_id, file_hash)` is unique, so the same file can't be stored twice for one user.

### Metadata stored

- **Per document:** owner, file name, type, size, page count, chunk count, status and failure reason, storage path, upload time, plus:
  - `file_hash` (sha256 of the file bytes),
  - `embedding_model`, `chunk_words` and `chunk_overlap` used to process it,
  - `pdf_title`, `pdf_author`, `pdf_created` from the PDF's own metadata (`pypdf`; empty if the PDF has none).
- **Per chunk:** document, owner, page, position, text, vector, plus `section`, the heading path in force on that page, such as `Risk Factors > Suppliers`.

**Sections come from two places.** (1) The PDF's bookmarks (its outline): each page gets the path of the last bookmark at or before it, nested bookmarks joined by ` > `. (2) A **heading found from the page layout**, with no word lists: the first one or two short lines in the top 35 percent of the page that are bold, set larger than the body text, or all capitals. Lines that repeat on many pages (running headers such as "Table of Contents") and lines that are mostly numbers or dates are skipped. A page's label is its bookmark path plus its heading when they differ (`Part II > Consolidated Balance Sheets`), or whichever exists. On a real 10-K this gives labels like `Advanced Micro Devices, Inc. - Consolidated Balance Sheets`; text pages get sensible but noisier headings, and about a quarter of pages have none. The heuristic can pick a bold table row (`(In millions) - Total Assets 33,341`) as a heading.

**Duplicates and stale documents.** Uploading a file whose hash the user already has gives 409 `duplicate`. If the existing copy failed, or is stale (below), the new upload replaces it instead. A document is **stale** when its `embedding_model` (which includes the processing recipe) differs from what the server uses now (or is empty, as for documents uploaded before this was tracked). Vectors made differently can't be compared, so stale documents are **skipped in searches** and shown with a warning and a **Re-process** button in the UI. Re-processing (`POST /documents/{id}/reprocess`) deletes the document's passages and rebuilds them in the background from the stored PDF with the current processing, keeping its chunk settings; it also works for failed documents (**Retry**). It answers 409 `already_processing` while a job is running and 409 `file_missing` if the stored PDF is gone (then delete and upload again). A different chunk size alone does not make a document stale, since the vectors are still comparable; the sizes are shown for information.

### Files on disk

```
docqa_files/
  users/{user_id}/documents/{document_id}/original.pdf
```

The folder is `DOCQA_STORAGE_DIR` (default `./docqa_files`, relative to where the server is started; it is in `.gitignore`). Search never reads the file; it reads only the `chunks` table. The original is kept for the future (opening the PDF at a cited page).

## Flow 1: ingestion (upload)

```mermaid
sequenceDiagram
  participant U as Browser
  participant A as API
  participant S as Storage
  participant D as Postgres
  participant B as Background job
  participant G as Embedding model
  U->>A: POST /documents (multipart PDF)
  A->>A: validate type, size, magic bytes, per-user count
  A->>D: insert document (status processing)
  A->>S: save original.pdf
  A-->>U: 202 + document
  A->>B: schedule ingest(document_id)
  B->>S: read PDF
  B->>B: extract text per page
  B->>B: chunk (300 words, 50 overlap)
  B->>G: embed chunks (batches of 8)
  B->>D: insert chunks + vectors, status = ready
  U->>A: GET /documents (polled every 2 s while processing)
```

### Validation at upload (synchronous)

| Check | Result |
|---|---|
| File name does not end in `.pdf` | 400 `unsupported_type` |
| Bigger than 20 MB | 413 `too_large` |
| Does not start with `%PDF` | 400 `not_a_pdf` |
| User already has 20 documents | 409 `too_many` |

### Processing (background)

1. **Extract.** `pypdf` reads each page's text. Rejected, with a message stored on the document and status `failed`: password-protected PDFs (those locked only with an owner password open normally), more than 600 pages, files that cannot be parsed, and PDFs with almost no text (under about 20 characters per page on average, which is what a scan looks like).
2. **Clean** (`clean.py`). pypdf's text is tidied before chunking, conservatively, so numbers and units are never touched:
   - **Running headers and footers** are removed: short lines among the first or last three lines of a page that repeat on at least 30 percent of pages (and at least 3). Lines that differ only by a page number at the start or end count as the same line. Numbers inside a line are not ignored, so a repeating table row such as `Total 100 200` is not mistaken for a header. A line that ends in a number counts as a footer only if those numbers rise from page to page (page numbers do), so rows such as `Total revenue 2023` and `Total revenue 1980` are kept.
   - **Page numbers** (`278`, `278 279`, `12 / 340`) are removed only when most pages have one alone on the very first or very last line. A stray figure at the edge of one page is kept.
   - **Unit lines** such as `(₹ in crore)` are never removed, even when they repeat, because they give meaning to the numbers below.
   - **Doubled titles** (`Consolidated Financial StatementsConsolidated Financial Statements`) are collapsed, and tabs and runs of spaces become one space.
   - **Rupee sign repair.** Some fonts map ₹ to a letter, so it is extracted as `(I in crore)` or `(H in crore)`. A stray `I`, `H` or backtick directly before `in crore` or `in lakh` is turned back into ₹. Installing `fontTools` did not fix this, so it is a targeted rewrite, limited to crore and lakh (Indian units).
   - On a real annual report (Reliance Industries Integrated Annual Report 2025-26, 147 pages) it removed about 0.8 percent of the words: the running header on every page and the doubled section title. All 79 unit lines were kept and most of the rupee signs were repaired. One document only; other layouts may behave differently. Page numbers printed on the third line of a page (as in that report's `278 279`) are not removed, because the rule is deliberately strict.
3. **Chunk.** Each page's text is split into windows of **300 words** that overlap by **50 words** (step 250). A chunk **never crosses a page**, so its page number is exact. A typical page of 400 to 600 words becomes two or three chunks. The cost: a sentence running over a page break is split between two chunks.
4. **Embed.** The local embedding model turns each chunk into a 768-number vector. The text it sees has a one-line header above the passage, `Document title | Section`, so a bare sentence like "the increase was driven by demand" is embedded together with where it comes from (see "Context header" below). It runs on the CPU at about a third of a second per 500-word chunk (measured here), so a 600-page document (roughly 1,000 chunks) takes about 4 to 5 minutes. The model (about 500 MB) downloads the first time it is used and takes about 20 seconds to load into memory on first use after each server start. With `DOCQA_EMBEDDING_PROVIDER=gemini` the chunks go to Gemini instead, in batches under about 12,000 tokens; the free tier then limits throughput to roughly 40 chunks a minute, and a `429` is retried after the wait Google asks for.
5. **Save.** All chunks are inserted in one transaction, together with the status change. If anything fails, nothing is half-saved: the chunks are rolled back and only the failure status and reason are stored.

The upload request returns immediately (202). The page polls the document list every two seconds until nothing is "processing".

## Flow 2: asking

```mermaid
sequenceDiagram
  participant U as Browser
  participant A as API
  participant G as Embedding model
  participant D as Postgres
  participant R as Reranker
  U->>A: POST /ask {question, documentIds, topK=5, candidates=30}
  A->>G: embed question
  A->>D: 30 nearest chunks, this user, ready documents only
  D-->>A: vector candidates
  A->>A: BM25 keyword search over the same chunks, merge both rankings (RRF)
  A->>R: score(question, each candidate)
  R-->>A: 30 relevance scores
  A->>A: sort by score, keep top N (default 5)
  A-->>U: candidates (before) + chunks (after)
```

### Stage 1: hybrid search (vector + keyword)

**Why.** A vector holds one summary of a whole chunk, so one specific sentence in a mixed chunk is diluted. Measured on the real Reliance report: the sentence "RIL contributes to over 30% of India's CBG production" scored 0.893 against the question when embedded alone, but its 200-word chunk scored 0.800 and ranked 145th, below tables of subsidiary names (0.82 to 0.84), so it never reached the reranker. The reranker, given the chunk, ranked it 4th of 300. The fix is to add a search that matches exact words and does not blur.

**How.** Two searches each return their best `candidates` (default 30):

- **Vector search** (below): chunks that mean the same as the question.
- **Keyword search**: BM25 (`bm25.py`, no dependency, k1 1.5, b 0.75) over the user's ready chunks. Text is lower-cased, split into words, a short list of question and glue words is dropped, and a trailing plural `s` is folded (`plants` matches `plant`). Rare terms weigh more than common ones, so `CBG` beats `production`. Chunks sharing no term with the question are not returned. Term counts are cached per chunk (keyed by id and a hash of the text).

The two rankings are merged by **reciprocal rank fusion**: each list gives a chunk `1 / (60 + rank)`, the two are added, and the best `candidates` are kept in that order. Only ranks are used, because vector and BM25 scores are on different scales. A chunk ranked well by both beats one ranked well by one; a chunk only one search finds can still get in. Chunks found only by keywords get their vector similarity looked up so every row still shows one. The merged list is the "before reranking" list; the reranker, cutoff and answer step follow unchanged.

On the real report (300-word chunks) the answer chunk moved from list position 30 (vector only, the last slot) to position 1, and the reranker put it first. At 200-word chunks it had been missing altogether.

**Two additions that need no LLM** (both on by default, measured in [DOCQA_EVAL.md](DOCQA_EVAL.md)):

- **The keyword search also sees each chunk's header** (document title and section or heading), so a company name or a statement title in the header can match the question.
- **Searching inside named documents.** When a question names some, but not all, of the documents being searched, `docmatch.py` finds them by matching the question's words against each title and file name (a title of `AMERICANEXPRESS_2022_10K` matches "American Express"; a year in the question, `FY2022` or `FY22`, must agree with the document's). A second vector and keyword search runs inside just those documents, and its two lists join the merge. This is a boost, not a filter: the search over all documents still runs, so a wrong guess cannot hide the right chunk. Abbreviations that are not in the title ("AMEX") do not match.

**Limits.** BM25 matches words, not meaning (no synonyms, light plural folding only, no other stemming), and it can pull in chunks that share several common words with the question. Each question loads the text of the user's eligible chunks to score them (fine at thousands of chunks, a few tenths of a second; with tens of thousands per user it gets slow and the per-chunk count cache, capped at 60,000 entries, is cleared when full; a Postgres full-text index or a persistent index would replace it). It does not fix flattened tables.

#### Vector search

The question is embedded into the same 768-dimension space. Postgres orders chunks by cosine distance (`embedding <=> query`) and returns the nearest `candidates` (default 30, max 100). The score shown is `1 - cosine distance`, so higher is better. The query always includes:

- `chunks.user_id = <current user>` (isolation),
- `documents.status = 'ready'`,
- `chunks.document_id IN (...)` when the user selected specific documents.

### Choosing the chunk size

Chunk size and overlap are chosen **per upload** (form fields `chunkWords` and `chunkOverlap`; the UI has two boxes next to the upload button). Defaults are 300 and 50. Allowed: size 100 to 800 words, overlap 0 to half the size. The values are stored on the document, and uploading the **same file again with different settings replaces the old copy**, which is how to re-chunk. The same file with the same settings is refused as a duplicate.

How it changes results:

- **Smaller chunks** (100 to 200 words): each chunk is about one idea, so matches are sharper and the context header counts for more. But an answer that spans several paragraphs gets split across chunks, results can look fragmentary, and there are more chunks, so uploads take longer and 30 candidates cover less text.
- **Larger chunks** (500 to 800 words): more surrounding context in each result and fewer chunks. But a chunk mixes several topics, so its vector is a blur and matches get fuzzier; the top 5 passages are longer to read.
- **Overlap** protects answers that straddle a boundary. More overlap means more near-duplicate chunks, which can fill the top 5 with the same text; 15 to 20 percent of the size is a sensible range. Zero overlap is allowed but risks cutting an answer in half.
- **Scores shift with size.** Both the vector similarity and the reranker score depend on chunk length, so the same passage scores differently at 150 and at 600 words. **The relevance cutoff (-2.5) was calibrated at about 300 words**; if you move far from that, re-check it.
- **Mixed sizes in one search are allowed** (vectors from the same model are comparable), but the ranking becomes uneven: a long chunk and a short one are not scored on equal terms, and the top 5 can favour one size. For fair comparisons, give all the documents you search together the same settings.
- A chunk never crosses a page, so a page shorter than the chunk size is one chunk whatever the setting. The size mostly matters for pages longer than the chunk size.
- There is no single best value; it depends on the documents. Try a few sizes on one document and compare the top 5 for questions you know the answers to.

### Context header

A passage on its own often lacks the context that makes it findable: "The increase was driven by strong demand" says nothing about what increased. So for **embedding and reranking only**, each passage gets a header: `Annual Report 2025 | Revenue > Cloud Services`, then a blank line, then the text. The title is the PDF's own title, or the file name without `.pdf` when the PDF has none, only a placeholder (`untitled`, `Microsoft Word - ...`, names ending in `.docx` and similar) or only a filing number (`0000764478-23-000041`; found on the evaluation filings, where it made the header useless). The section is left out when the PDF has no bookmarks. The header is capped at about 400 characters.

The stored text and what the UI shows are the PDF's own words, without the header. The question is embedded as typed.

Check on three passages with a question about cloud revenue growth: without the header, a passage about hiring (similar wording, "the increase was driven by strong demand ... twelve percent") scored 0.718 and the cloud passage 0.707, so the wrong one ranked first. With the header, the cloud passage scored 0.890 and the hiring one 0.763. This is a small hand-made example, not a benchmark.

The processing recipe (cleaning and header) is part of the stored `embedding_model` name, for example `jinaai/jina-embeddings-v2-base-en | title+section+clean+heading`. Documents made under a different recipe therefore count as stale and must be re-processed (or uploaded again).

### Stage 2: reranking (cross-encoder)

Vector search compares two precomputed vectors, so each chunk is summarised without knowing the question. A **cross-encoder** reads the question and one chunk together in a single pass and outputs one relevance score. It is slower per item but more accurate, so it is only run on the 30 candidates. The results are sorted by score and the best `topK` (default 5, max 5) are kept.

- Scores are relative and can be negative; only the order matters.
- The model runs inside the server process (ONNX on CPU). It is loaded on first use (a download of about 150 MB the first time ever), then cached in memory behind a lock.
- A cross-encoder is a fixed relevance judge. It cannot follow instructions such as "prefer the latest year". An LLM reranker could, at the cost of speed, money and stability; it would sit behind the same function in `rerank.py`.

### Relevance cutoff (optional)

Ranking alone cannot say whether any passage answers the question, so a vague or unanswerable question still returns the 5 closest chunks. A cutoff (default **-2.5**, set with `DOCQA_MIN_RERANK_SCORE`, or `off`; a request's `minScore` overrides it, and `null` means none) removes reranked results scoring below it from `chunks`. The response reports `droppedBelowCutoff` and the `minScore` applied; when `chunks` is empty but `candidates` is not, the UI shows "No relevant passages found". The cutoff applies only when reranking is on, and `candidates` (the "before" list) is never filtered. The default was chosen by running the real reranker on 9 answerable and 9 unanswerable questions over report-style passages: answerable best scores ranged from -1.87 to 2.6 and unanswerable from -4.67 to -2.66, so -2.5 sits in the gap. It is a small synthetic test, so the value should be re-checked on real documents: if real answers get hidden, lower the number (for example -3.5); if junk shows up, raise it. **On the real Reliance report it filtered nothing** (irrelevant chunks scored about -0.3), so it needs recalibrating (see Next steps). The UI box starts at the server default (it reads it from `/config`).

### Stage 3: answer generation (optional, off by default)

With `"generate": true`, the final chunks are numbered and sent to Gemini with an instruction to answer **only** from them, cite them like `[1]`, and say it could not find the answer if the passages do not contain it. `[n]` is the n-th item of the final ("After reranking") list. The UI has a checkbox in the settings row; the answer appears in a card above the results with its sources listed, and the reranked items are labelled `[1]`, `[2]`... to match.

- **Failure is not fatal.** If Gemini errors (no key, rate limit), `/ask` still returns 200 with the passages and `answerError`; the UI shows the message above the results.
- **No relevant passages:** when the cutoff removes everything, Gemini is not called and `answer` is null.
- **Chosen model:** Gemini free tier, because it was already wired in. Trade-off: Google may use the prompt content to improve its products on the free tier, and the free rate limit applies. Alternatives considered: Groq, local Ollama (fully private, heavier and weaker), OpenRouter free models.
- Answers about numbers in tables can be wrong because tables are flattened (see limitations); the citations are there to check.

### Response shape

```json
{
  "answer": null, "answerError": null,
  "droppedBelowCutoff": 0, "minScore": null,
  "candidates": [ { "chunkId": 41, "documentId": 3, "filename": "report.pdf", "page": 12, "section": "Risk Factors > Suppliers",
                    "text": "...", "vectorRank": 1, "vectorScore": 0.7312,
                    "rerankRank": 4, "rerankScore": -0.21 }, "... 30 items, vector order ..." ],
  "chunks":     [ { "...same fields...", "vectorRank": 5, "rerankRank": 1, "rerankScore": 3.84 },
                  "... 5 items, reranked order ..." ]
}
```

`candidates` is the "before" list (merged vector and keyword order; `rank` is the position, `vectorRank` and `keywordRank` are null when that search did not return the chunk). `chunks` is the "after" list. Each item in `chunks` knows where it came from (`vectorRank`) and where it ended up (`rerankRank`).

## API reference

All paths are under `/api/docqa`. Errors use `{"detail": {"error": "<code>", "message": "<text for the user>"}}`.

| Method and path | Purpose | Success | Errors |
|---|---|---|---|
| `GET /config` | `enabled`, the default `minScore`, and the chunk defaults and limits (`chunkWords`, `chunkOverlap`, `minChunkWords`, `maxChunkWords`); the UI uses it to show or hide the tab and to prefill its boxes | 200 | |
| `GET /documents` | The user's documents, newest first | 200 | 401, 503 |
| `POST /documents` | Upload one PDF (multipart field `file`, optional `chunkWords` and `chunkOverlap`) | 202 + document, status `processing` | 400 `unsupported_type` `not_a_pdf` `bad_chunk_size` `bad_overlap`, 413 `too_large`, 409 `too_many` `duplicate` `already_processing` (the same file is still being processed), 401, 503 |
| `POST /documents/{id}/reprocess` | Rebuild a stale or failed document from its stored PDF (same chunk settings) | 202 + document, status `processing` | 404 `not_found`, 409 `already_processing` `file_missing`, 401, 503 |
| `DELETE /documents/{id}` | Delete the document, its chunks and its files | 204 | 404 `not_found` (also for another user's document), 401, 503 |
| `GET /models` | Gemini models that can write answers for this server's key (`default` and `models`: `id`, `name`); from Google's model list, cached 10 minutes; needs a signed-in user | 200 | 503 `model_unavailable` (no key, unreachable), 401, 503 `docqa_disabled` |
| `POST /ask` | Search | 200 | 400 `empty_question`, 503 `model_unavailable`, 401, 503 `docqa_disabled` |

`POST /ask` body:

| Field | Default | Meaning |
|---|---|---|
| `question` | required, 1 to 2000 characters | |
| `documentIds` | all | Limit the search to these documents. Leave it out for all of the user's documents. `[]` gives 400 `no_documents`; a list with no searchable document (deleted, processing, stale, not yours) gives 400 `no_searchable_documents`; unsearchable ids next to a usable one are ignored |
| `topK` | 5 (1 to 20) | How many results to return after reranking; the UI has a "Results to show" box. The pool of `candidates` is never smaller than `topK` |
| `candidates` | 30 (1 to 100) | How many to fetch before reranking |
| `rerank` | true | `false` returns vector order only |
| `minScore` | server default (-2.5); `null` = none | Hide reranked results scoring below this number |
| `generate` | false | `true` adds a Gemini `answer` (or `answerError` if it fails) |
| `model` | server default | Gemini model for the answer (with `generate`); must be one listed by `GET /models`, else 400 `bad_model` |
| `hybrid` | true | `false` skips the keyword (BM25) search and uses vector results only |

A `401` means login is switched on and there is no valid session. With login off, everyone is the shared local user.

## Security and privacy

- **Isolation.** Every query filters by the owner's user id. Another user's document id returns 404, never 403, so it does not reveal that it exists. A test covers this.
- **Auth.** The user comes from the main app's `current_user` dependency (HttpOnly signed session cookie when Google sign-in is on).
- **Uploads.** Extension, size and `%PDF` header are checked; the storage path is built from numeric ids only (never from the file name), and `storage.py` refuses any key that escapes its root. The file name is stored for display only.
- **Data sent to Google.** By default none: embedding and reranking both run locally. Text goes to Gemini only if you set `DOCQA_EMBEDDING_PROVIDER=gemini` or ask for `generate`. On the **free tier, Google may use that content to improve its products**, so do not send sensitive documents that way.
- **Secrets.** `GEMINI_API_KEY` is read from the environment only and is never returned to the browser or logged.
- **Not done yet:** rate limiting on `/ask` and uploads, virus scanning, encryption at rest for stored files.

## Errors and edge cases

| Situation | Behaviour |
|---|---|
| Scanned PDF | Status `failed`: "no readable text (it looks scanned)" |
| Password-protected or corrupt PDF | Status `failed` with a plain message. PDFs locked only with an owner password (they open without a password) are read normally |
| Over 600 pages | Status `failed` with the page count |
| Gemini key missing, wrong or rate limited (only with the `gemini` provider or `generate`) | Clear message; a rate limit is retried after Google's requested wait; a daily limit is reported as such; a busy service (500, 502, 503, 504) is retried up to four times with 3, 6, 12 and 24 second waits, then "busy right now, try again in a minute" |
| Unexpected crash while processing or while saving the passages (a bad vector, text the database refuses, the document deleted meanwhile) | Chunks rolled back, status `failed` with a generic message, so it never stays on "Processing"; details in the server log. Use **Retry** |
| Question when nothing is ready | Empty candidate list: "No passages found" |
| Deleting while processing | The rows and files are removed. The job may log an error when it tries to save, but nothing is kept |
| Server restart mid-processing | The job is lost (it is in-process), so the document stays "processing". Delete and re-upload. A real job queue is a future step |

## Testing

Tests live in `backend/tests/` (`test_docqa.py`, `test_bm25.py`, `test_clean.py`, `test_docmatch.py`, `test_extract.py`, `test_models_list.py`, `test_providers_retry.py`). The model calls are replaced by fakes so the tests need no network or key: a deterministic word-hash embedder (replacing the local model), a fake answer, and a fake reranker. The Postgres-backed ones need a local Postgres with pgvector and an empty database called `docqa_test` (`createdb docqa_test`; override with `DOCQA_TEST_DATABASE_URL`); without it they are skipped.

They cover: upload then ready, ranked chunks with correct page, the `topK` and `generate` options, selecting documents, delete removing chunks, rejecting non-PDFs, scanned-PDF failure, isolation between users, the disabled state, reranking changing the order, reranking switched off, and the chunker keeping pages and overlap, hybrid search finding an exact term the vector search misses, searching inside documents a question names, the document-selection rules (`no_documents`, `no_searchable_documents`), the model list and chosen-model checks, owner-locked PDFs (read) versus password-protected ones (rejected), NUL bytes and layout headings in extraction, and retrying a busy Gemini service. The Gemini calls themselves are stubbed.

What is **not** tested automatically: the real embedding model and reranker inside the server (both were checked by hand, and they run for real in the evaluation harness, see [DOCQA_EVAL.md](DOCQA_EVAL.md)), real Gemini responses, and the browser UI.

## Deploying

Not deployed. Before it can go on Render:

- **Postgres with pgvector.** Check that the chosen plan supports the extension, or use a provider that does (Neon, Supabase).
- **Persistent file storage.** Render's disk is wiped on each deploy. Use an S3-compatible bucket such as Cloudflare R2 by replacing `storage.py`; keys are already `users/{id}/documents/{id}/original.pdf`.
- **Memory.** The embedding model (about 500 MB on disk) and the reranker both live in the server's memory, far over the free 512 MB web service. Use a larger instance or a separate worker, or switch both to hosted APIs.
- **Background work.** Ingestion runs inside the web process. Large uploads on a sleeping free instance can be cut off; a queue and a worker are the real fix.
- **Secrets and limits.** Set `GEMINI_API_KEY` if you use answers or Gemini embeddings, and add rate limiting before exposing it publicly.

---

# Part 3: Status and next steps

## Status

Built and working: upload and processing, hybrid search (meaning plus keywords), reranking with a relevance cutoff, adjustable chunking, document selection, optional cited answers from Gemini with a model dropdown, and the before/after ranking view. 126 backend tests pass (`cd backend && .venv312/bin/python -m pytest -q`); the frontend type-checks and builds. Not deployed: the Render deployment is the backtester only.

## Known limitations

- One chunk per page, so context across page breaks is lost.
- Tables are flattened to text (cleaning does not restore their structure), which hurts questions about numbers in tables. Chunking can split a table and separate its rows from the column headers.
- Printed page numbers can differ from PDF page numbers (some reports use two-page spreads), so a cited page is the PDF page.
- No OCR.
- The first upload or question after each server start is slow (the models load into memory, about 20 seconds). CPU speed limits large uploads.
- In-process background jobs are lost on restart.
- No migration tool (new columns are added automatically; other schema changes are not).
- Embedding model or recipe changes make every document stale until it is re-processed (stale ones are skipped in searches until then).
- Section labels come from bookmarks and a layout heuristic for headings; PDFs with neither (and pages the heuristic misses) have none, and some detected headings are noise.
- The relevance cutoff does not filter on real documents yet (see Findings).
- Each question is independent: no conversation memory.
- Retries on a rate-limited or busy Gemini wait inside the request (a rate limit up to about 66 seconds per attempt, a busy service 3 to 24 seconds), so a slow Gemini can hold a request for minutes before the friendly error; the browser may give up first. A shorter cap or a job queue would fix it.
- Answers are only as good as the retrieved passages; a miss shows up as "could not find it in the documents".
- Keyword search is BM25 over words (no synonyms, light plural folding) and scores the user's chunks in memory on each question.
- No automated evaluation of answer quality.

## Findings from real documents

- **Real report inspected:** Reliance Industries Integrated Annual Report 2025-26 (147 PDF pages, about 900 words per page, up to about 1,900).
  - **No bookmarks**, so `section` comes only from the layout heading (which can be found on most statement pages).
  - The running header was on nearly every page (now removed by cleaning) and section titles were doubled (now collapsed).
  - The rupee sign is extracted as `I`, `H` or a backtick; a narrow rewrite repairs it before "crore" and "lakh" (installing `fontTools` did not help).
  - **Tables are flattened** into runs of numbers, with column headers far from the rows and often in other chunks. Keeping the grid (row and column reconstruction with `pdfplumber`) was tested and did **not** improve retrieval on FinanceBench; the main table problem there is a vocabulary gap (see Next steps and [DOCQA_EVAL.md](DOCQA_EVAL.md)).
  - Some pages are two-page spreads ("278 279"), so a cited PDF page is not the printed page number. Page numbers on the third line of a page are not removed (the rule is deliberately strict).
- **Retrieval miss that led to hybrid search.** For "What percentage of India's CBG production does RIL contribute to?" the sentence "RIL contributes to over 30% of India's CBG production" was on page 15, in a 200-word chunk that ranked 145th by vector similarity (0.800 against 0.822 for the 30th), below tables of subsidiary names, so the reranker never saw it. Embedded alone, the sentence scored 0.893 against the question; the reranker, given the chunk, ranked it 4th of 300. The vector of a mixed chunk dilutes one specific sentence. With hybrid search it moved to candidate position 1.
- **The -2.5 cutoff is too loose on real documents.** It was calibrated on made-up passages. On the real report, irrelevant chunks scored about -0.3 and passed, so an unanswerable question still returns five results.
- **The revenue question** ("What was Reliance Industries's revenue in FY2026?") still returned weak results (subsidiary financials, segment text), which points at flattened tables.
- **Why local models:** the first design used Gemini embeddings; the free tier (about 30,000 tokens per minute) made uploads take many minutes and hit quota errors. Gemini stays as an option.
- **Vector and reranker scores are different scales** and not comparable. Only the reranker score is used for the cutoff.
- **Stale documents.** Each document records the embedding model plus a recipe tag (`title+section+clean+heading`). Any change to cleaning, the header or the model must bump `EMBED_RECIPE` in `docqa/config.py`, which marks older documents stale until they are re-processed.
- **Retrieval measured on FinanceBench** (first run): top-5 page recall about 0.48 in one document and 0.33 across several; tables are the weak spot. See [DOCQA_EVAL.md](DOCQA_EVAL.md).

## Next steps

1. **Evaluate retrieval on a public dataset (five experiments done; LLM question expansion is the big lever).** Harness: `backend/evals/`. On FinanceBench (12 filings, 52 questions) the baseline found the evidence page in the top 5 for about half the questions in one document and a third across several; titles, layout headings and name matching lifted the multi-document figure from 0.33 to 0.44. A ceiling test (search with the page's own text) reaches 1.00, so the index is not the limit: the wording gap between question and page is. Having an LLM write a short description of the page that would answer each question, searching with it, and reranking against it raised top-5 recall to **0.87 (one document) and 0.83 (all documents)**, and for table questions from 0.22 to 0.83. Caveat: the descriptions were written by Claude, not Gemini; the next step is to rerun with Gemini, then decide whether to build it into the app as an opt-in setting (one extra LLM call per question). Details and the full log: [DOCQA_EVAL.md](DOCQA_EVAL.md).
2. **Fix what fails most.** Likely candidates:
   - **Tables, vocabulary gap:** table questions mostly fail because the question names a concept (quick ratio, gross margin, liquidity) that the statement page never mentions. Tag statement pages by title and add the vocabulary people ask about, or expand the question with an LLM. Re-gridding the table (tested with `pdfplumber`, MIT) did not help retrieval; it may still help answer quality. PyMuPDF is good but AGPL, which conflicts with this MIT repository.
   - **Sections without bookmarks:** use each page's running header or match known annual-report headings.
   - **Parent-child chunks:** match small chunks, show the larger passage.
   - **Question splitting for broad questions** (an opt-in checkbox: an LLM splits the question, each part is searched, the results are combined).
3. **Recalibrate the -2.5 cutoff** on real documents, and tell the user the number to use.
4. **Smaller ideas:** show only the sources an answer cites; a "Re-process" button using the stored PDF; open the PDF at a cited page; conversation memory; slower polling while uploading; multi-file upload; a larger file limit (a 600-page PDF with images may exceed 20 MB); weights for the keyword/meaning merge; deployment work (S3 storage, job queue, rate limiting).

## Decisions and why

| Decision | Reason |
|---|---|
| Separate package, database and tables | The two features are unrelated; separation lets either one change or be removed without touching the other |
| Postgres + pgvector, not a separate vector database | One system to run; the per-user filter is ordinary SQL |
| Same Postgres in dev and prod | pgvector does not exist in SQLite; two code paths would hide bugs |
| Local reranker and local embeddings, not APIs | Free, no key, no quota, deterministic, and documents never leave the machine. The first design used Gemini embeddings and hit the free rate limit, making uploads take minutes |
| `jina-embeddings-v2-base-en` | 768 dimensions and an 8,000-token input; the common BGE models cut text off at 512 tokens, which is shorter than a 300 to 500 word chunk can be |
| Cross-encoder before LLM reranking | Cheaper and more stable; LLM can be added behind the same function |
| Chunk never crosses a page | Exact page citations matter more than a few split sentences |
| 300 words / 50 overlap as the default, chosen per upload | Smaller chunks give sharper matches and cheaper reranking; the overlap of about 17% protects boundaries. Easy to change in `config.py` if results look too fragmented |
| 30 candidates, 5 results by default | Wide enough that reranking can rescue a missed passage, small enough to be fast |
| No vector index | Exact search is correct and quick at this size |
| Show before and after | So the value of reranking can be judged on real documents, not assumed |
| Store the embedding model and chunk settings with each document | So a model change is detected, stale vectors are never mixed into a search, and the user is told what to re-process |
| Clean extracted text conservatively (repeated edge lines, doubled titles, rupee sign) | Annual reports repeat a header on nearly every page; left in, it is embedded into every chunk. Rules are strict because wrongly deleting a figure is worse than leaving noise |
| Prepend title and section to each passage for embedding and reranking | Gives short, vague passages the context they lack; measured to fix a wrong top result in a small test. The stored text stays clean |
| Section from PDF bookmarks, not guessed from text | Bookmarks are the author's own structure and exact; heading detection from raw text is unreliable and would add noise |
| File hash | Cheap duplicate detection; avoids double results and wasted processing |
| Feature flag by `DOCQA_DATABASE_URL` | Safe to ship without affecting the existing deployment |
