# Document Q&A: retrieval evaluation plan

**Status: harness built (`backend/evals/financebench_retrieval.py`); baseline plus five experiments done, results below.** This describes how we measure the retrieval part of [Document Q&A](DOCQA.md) on a public dataset instead of a hand-made one, so changes can be judged by numbers and not by trying a few questions. **Section 13 is the running log** of what got stuck, how it was fixed and what it changed; add to it with every experiment. Design background, current state and open problems are in [DOCQA.md](DOCQA.md) (Part 2 and Part 3).

## Results at a glance

The test: 52 questions about 12 company filings (FinanceBench). For each question we check whether the page that holds the answer is among the first 5 results. Updated 2026-10-18. The detailed numbers and the story behind each step are in section 13; terms are defined in the glossary below.

**Table 1: how often the right page is in the top 5 results (higher is better)**

| Step | What changed | Search inside one document | Search across all 12 documents |
|---|---|---|---|
| 1 | **Starting point** (the system as first tested) | 48% | 33% |
| 2 | Tried keeping the table grid (rows and columns); dropped, no help | 46% | 33% |
| 3 | Added titles to the keyword search, and searched inside documents the question names | 48% | 35% |
| 4 | Added page headings and fixed unusable PDF titles (**current system**) | 50% | 44% |
| 5 | Added an LLM-written description of the answer page to the search; the reranker still scores the plain question | 58% | 54% |
| 6 | Same, and the reranker also scores against the description (**best so far**) | **87%** | **83%** |
| | Perfect-query ceiling (the best the index could do) | 100% | 100% |

**Table 2: how high the right page ranks (MRR, higher is better, 1.00 is perfect)**

| Step | One document | All 12 documents |
|---|---|---|
| 1 Starting point | 0.337 | 0.274 |
| 2 Table grid | 0.319 | 0.250 |
| 3 Titles and name search | 0.347 | 0.284 |
| 4 Headings and title fix (current) | 0.374 | 0.348 |
| 5 LLM description, plain-question rerank | 0.421 | 0.380 |
| 6 LLM description, description rerank (best) | **0.665** | **0.627** |
| Ceiling | 0.952 | 0.925 |

**Table 3: questions whose answer is in a table (18 of the 52), right page in the top 5**

| Step | One document | All 12 documents |
|---|---|---|
| 1 Starting point | 22% | 11% |
| 4 Headings and title fix (current) | 22% | 28% |
| 6 LLM description, description rerank | **83%** | **83%** |

**Abbreviations and terms**

- **Top 5 / R@5:** the share of questions where the correct page is among the first 5 results. R@30 is the same for the first 30 (the candidates that go to the reranker).
- **MRR (mean reciprocal rank):** 1 divided by the position of the first correct result, averaged over questions. Position 1 scores 1.00, position 2 scores 0.50, position 5 scores 0.20, not found scores 0.
- **Rerank:** a second model re-scores the 30 candidates and keeps the best 5. **Hybrid:** meaning-based search and keyword search combined.
- **LLM description / expansion:** a language model writes a short paragraph describing the page that would answer the question (statement titles, line items, standard terms); the search uses the question plus that paragraph. Steps 5 and 6 used descriptions written by a Claude subagent, not Gemini.
- **Ceiling / oracle:** searching with the answer page's own text instead of the question, to see the best possible result.
- **One document / all 12:** searching only the document the question is about, or all 12 together as a real user with many reports would.
- **Table grid:** rebuilding a table's rows and columns from the PDF's word positions (tried with `pdfplumber`).
- **FinanceBench:** the public set of questions about company filings (10-K annual reports, 10-Q quarterly reports) used here.

Caveats: 52 questions, one run per setting, chunk size 300; steps 5 and 6 still need a rerun with Gemini; the step 6 variant was chosen after seeing step 5 (a small selection effect).

## Glossary (terms used in this document)

- **Evidence page:** the page of the filing that holds the answer to a question, as labelled in the dataset. Our "hit" means a returned chunk comes from that page.
- **R@k (recall at k):** the share of questions whose evidence page appears among the first k returned chunks. R@5 = 0.50 means half the questions have it in the top 5.
- **MRR (mean reciprocal rank):** for each question take 1 divided by the position of the first correct chunk (position 1 gives 1.00, 2 gives 0.50, 3 gives 0.33, 5 gives 0.20, not found gives 0), then average over questions. It rewards ranking the right page higher, which R@k ignores. 0.665 means the right page is typically at position 1 or 2; 1.0 is perfect.
- **Candidates / pool (R@30):** the 30 chunks the search hands to the reranker. R@30 is how often the right page is among them at all; if it is not, the reranker cannot rescue it.
- **Single scope / shared scope:** search inside the question's own document, or across all 12 documents at once.
- **Hybrid:** vector search (meaning) plus keyword search (BM25), merged. **Rerank:** a second model re-scores the 30 candidates and keeps the best.
- **Oracle:** a ceiling test that searches with the evidence page's own text instead of the question, to show the best the index could ever do.
- **Expansion ("expand"):** adding text to the question before searching. An LLM writes a short description of the page that would answer the question (statement titles, line-item names, standard terms), in the page's own vocabulary, without answering and without numbers. **The search query is the original question plus that description**, not the description alone. Example: question "What was the largest liability in American Express's Balance Sheet in 2022?" plus description "American Express consolidated balance sheets December 31, 2022: total liabilities, customer deposits, long-term debt, card member receivables, accounts payable ...".
- **Expanded text:** that description paragraph (about 30 to 50 words). "Rerank against the expanded text" means the reranker scores each page against question plus description, instead of the bare question.
- **Who wrote the descriptions:** in the experiments reported here, a Claude subagent that saw only the question text. In the product the writer would be Gemini (or another selected model). The two have not been compared yet.
- **Table-like evidence:** an evidence page whose text is at least 40 percent numeric tokens (a digit-density test, not a human judgement).

## 1. Goal

Find out how often the system puts the page that contains the answer in front of the user, and where it fails. Part 1 covers **retrieval only** (search, merge, rerank). Answer generation (Gemini) is evaluated later, in a separate part.

Retrieval needs **no LLM**. A labelled question says which page holds the evidence; we run the real search and check whether a returned chunk is on that page. Nothing is sent to Google and no API key is needed.

## 2. Why this matters now

Several problems were found by hand on one report (the CBG question: the answer chunk ranked 145th by vector search and never reached the reranker; flattened tables; a cutoff that filters nothing). Each fix so far was judged on one or two questions. With a labelled set we can tell whether a change helps in general, and which problem costs the most.

## 3. Dataset: FinanceBench

- 150 questions about real company filings (mostly US 10-Ks, some 10-Qs, 8-Ks and annual reports) across 84 documents, from Patronus AI: `github.com/patronus-ai/financebench`.
- Each question has the **evidence text and its page number** (`evidence`: `evidence_text`, `evidence_page_num`, `doc_name`, and the full page text). A question can have more than one evidence item (1.26 on average).
- Three question types, 50 each: `metrics-generated` (figures from the statements), `domain-relevant` (general finance questions about a company) and `novel-generated` (written by analysts).
- The PDFs are public in the same repository (`pdfs/`).
- Licence: the GitHub repository shows **no licence file** and its README does not state one, so treat the data as internal-evaluation-only. The dataset and PDFs are **downloaded into a folder outside this repository and never committed or redistributed**.

Why not the others:

| Dataset | Why not (for part 1) |
|---|---|
| BEIR (FiQA, SciFact, ...) | Short web or abstract passages, no long documents or tables; would not show our real weak spots |
| FinQA, TAT-QA, ConvFinQA | Table-centred but on short extracted snippets, not whole reports |
| DocFinQA | Long documents but no PDF pages, so a page-based check is not possible |

Limits to keep in mind: these are US filings, so the layout differs from Indian annual reports such as Reliance's; and the questions often name the company ("for 3M"), which makes a search across many documents harder than a search inside one.

## 4. What counts as a hit

Our chunks never cross a page, so a chunk has an exact page. For a question with evidence pages `P` in document `D`:

- **Hit at k:** at least one of the first `k` results is a chunk of document `D` on a page in `P`.
- The dataset's page numbers are **0-based** (confirmed: matching the evidence text against our extracted pages gives found minus labelled = 1 on every located item in the smoke test). The harness does not trust the label: it finds the page(s) whose text contains at least 40 percent of the evidence's word triples (all pages within 0.05 of the best), reports the share located and the offsets, and excludes questions it cannot locate, counting them.

## 5. Metrics

- **Recall@k** for k = 1, 3, 5, 10 and for the whole candidate pool (30): the share of questions with a hit.
- **MRR**: the mean of 1 / (rank of the first hit), 0 when none. It rewards putting the right page higher.
- Optionally **nDCG@10** with all evidence pages as relevant.

Each is reported **per stage**, because the stages fail differently:

| Stage | List measured |
|---|---|
| Vector pool | the 30 nearest by meaning |
| Keyword pool | the 30 best BM25 matches |
| Hybrid pool | the merged 30 (what the reranker sees) |
| Final | the reranked top 5 (what Gemini would see) |

If the hybrid pool recall is high but the final recall is low, the reranker is at fault. If the pool recall is already low, the reranker never had a chance.

## 6. Configurations to compare

1. Vector only (`hybrid: false`, no rerank).
2. Hybrid, no rerank.
3. Hybrid + reranker (the current system).
4. Chunk size 200, 300 and 500 words (overlap about 17 percent of the size). Each size means ingesting the documents again.
5. Later, once built: the weighting in the merge, table-aware extraction, and the cutoff value.

Two search scopes for every configuration:

- **Single document:** the search is limited to the question's own document (`documentIds`). Measures extraction, chunking and ranking.
- **Shared corpus:** all selected documents are searched together, as a real user with several reports would. Measures whether the right company's pages win.

## 7. Breakdowns that show where we are lacking

- By question type (the three types above).
- **Table vs text evidence.** An evidence page is called table-like when most of its evidence text is numbers (a digit-density threshold, recorded in the report). Expected: much lower recall on tables.
- By evidence position and document length (does it get worse on long filings?).
- A list of the **misses**, with the question, the expected page, and what was returned, to read by hand.

## 8. Method

1. A script, `backend/evals/financebench_retrieval.py` (not part of the app, not imported by it), reads the question file and the PDFs of the chosen subset from a data folder outside the repository.
2. It uses its **own database** (`docqa_eval`) and a dummy user id, so real uploaded documents are never touched. It ingests each PDF with the real pipeline (extract, clean, chunk, embed), with fixed chunk settings per run.
3. For every question it calls `pipeline.retrieve` and `pipeline.rerank` directly (no HTTP) for each configuration and scope, and records the ranked pages.
4. It writes a per-question CSV and a summary table. Summaries worth keeping are copied into this document under "Results".

Everything is deterministic given the same documents and settings, so a run can be repeated after a change and compared. Documents already ingested with the same settings are reused, so only the first run is slow.

### How to run it

```bash
# 1. Data folder outside the repository, e.g. ~/financebench-data with:
#      questions.jsonl   (raw.githubusercontent.com/patronus-ai/financebench/main/data/financebench_open_source.jsonl)
#      pdfs/<doc_name>.pdf   (raw.githubusercontent.com/patronus-ai/financebench/main/pdfs/<doc_name>.pdf)
#      top12.txt          (one doc_name per line: the 12 documents with the most questions)
# 2. A separate evaluation database (never your real one; the script refuses "docqa"):
createdb docqa_eval
# 3. From backend/:
python -m evals.financebench_retrieval --data-dir ~/financebench-data
#    options: --chunk-words 300 --overlap 50 --pool 30 --only DOC1,DOC2 (smoke test) --no-rerank
#    --bm25-header --name-boost   match the current system's query-time features (the app has them on by default)
#    --extractor plumber          experimental table-grid text (needs pdfplumber)
#    --oracle                     ceiling test: search with the evidence text instead of the question
#    --expand                     search with the question plus an LLM-written description of the answering page
#                                 (needs GEMINI_API_KEY unless the cache file is complete; sends the questions to Google;
#                                 cached in <data-dir>/<--expansions-file>, default expansions_gemini.json)
#    --rerank-expanded            with --expand: the reranker also scores against the expanded text
#    --tag _name                  suffix for the results folder
```

It writes `results/c<chunk>_o<overlap>/per_question.csv` (one row per question, scope and configuration, with the first hit rank, the expected pages and the top five pages returned) and `summary.md` into the data folder. Each chunk size uses its own dummy user, so several sizes can sit in the same evaluation database.

## 9. Cost and time

Embedding runs on the CPU at about a third of a second per chunk. A 10-K of 150 to 300 pages is roughly 600 to 1,500 chunks, so **5 to 8 minutes per document**; all 84 documents would take many hours. So:

- **Start with about 12 documents** (those with the most questions), giving roughly 50 to 60 questions, in about an hour.
- Each additional chunk size repeats that ingest for the subset.
- Retrieval itself is fast (well under a second per question per configuration).

## 10. What this will not tell us

- Whether **answers** are correct (needs the LLM; a later part, using the dataset's reference answers).
- Quality on **Indian annual reports** specifically; US filings are a proxy. A small hand-labelled set on the Reliance report can complement it later.
- Quality on scanned documents (not supported) or other languages.
- Scores are on a few dozen questions, so small differences (a point or two) are noise; look at large gaps and at the misses themselves.

## 11. Findings so far

Running the harness found several real bugs in the product, all fixed (with tests):

- **PDFs locked only with an owner password were rejected** as "password protected" (the Best Buy 10-Q). Many filings are permission-locked but open with an empty password; the extractor now tries that first.
- **NUL bytes in extracted text crashed processing.** Checkbox glyphs in a 10-Q extracted as `\x00`, which Postgres text columns refuse, so the document failed with a generic error. They are now replaced by spaces. (It recurred once through the new heading text and was fixed there too.)
- **PDF titles that are only filing numbers** (`0000764478-23-000041`, 6 of the 12 documents) went into the embedding header and defeated name matching; the file name is used instead.
- **A single 503 ("high demand") from Gemini failed the whole call.** Transient errors (500, 502, 503, 504) are now retried with a short backoff.

## 12. Results

### Run 1: 2026-10-18, chunks 300/50, pool 30, 12 documents, 52 questions

Documents: AMD, American Express, Boeing, PepsiCo, Amcor, 3M (10-K and Q2 10-Q), AES, Best Buy (10-K and Q2 10-Q), CVS Health 2022, Ultra Beauty Q4 2023 earnings (the twelve with the most questions). Embedding the documents (about 4,800 chunks) took about 14 minutes (about 0.17 seconds per chunk), faster than the estimate, and the whole run took about 19 minutes. All 64 evidence items were located on a page (the dataset's page numbers are 0-based). Question mix in this subset: 33 domain-relevant, 16 novel, 3 metrics.

R@k = share of questions whose evidence page appears in the first k chunks. MRR = mean of 1 / first-hit rank. With 52 questions, a difference of 0.05 to 0.08 is one or two questions, i.e. noise.

**Search inside the question's own document (single)**

| config | R@1 | R@3 | R@5 | R@10 | R@30 | MRR |
|---|---|---|---|---|---|---|
| vector | 0.19 | 0.37 | 0.44 | 0.62 | 0.77 | 0.313 |
| keyword (BM25) | 0.19 | 0.29 | 0.35 | 0.40 | 0.58 | 0.267 |
| hybrid | 0.15 | 0.33 | 0.42 | 0.58 | 0.75 | 0.285 |
| vector + rerank | 0.19 | 0.40 | 0.50 | 0.62 | 0.77 | 0.328 |
| **hybrid + rerank (current system)** | 0.21 | 0.40 | **0.48** | 0.62 | 0.75 | 0.337 |

**Search across all 12 documents (shared)**

| config | R@1 | R@3 | R@5 | R@10 | R@30 | MRR |
|---|---|---|---|---|---|---|
| vector | 0.15 | 0.25 | 0.37 | 0.54 | 0.65 | 0.241 |
| keyword (BM25) | 0.08 | 0.12 | 0.15 | 0.25 | 0.38 | 0.124 |
| hybrid | 0.13 | 0.17 | 0.23 | 0.35 | 0.65 | 0.202 |
| vector + rerank | 0.15 | 0.29 | 0.35 | 0.48 | 0.65 | 0.260 |
| **hybrid + rerank (current system)** | 0.17 | 0.29 | **0.33** | 0.50 | 0.65 | 0.274 |

**Table-like versus text evidence, single scope (R@5 / MRR)**

| config | table (n=18) | text (n=34) |
|---|---|---|
| vector | 0.28 / 0.246 | 0.53 / 0.349 |
| vector + rerank | 0.28 / 0.156 | 0.62 / 0.419 |
| hybrid + rerank | 0.22 / 0.135 | 0.62 / 0.444 |

### What the numbers say

1. **The current system finds the evidence page in its top 5 for about half the questions** (0.48 in a single document, 0.33 across documents). A quarter of the questions (13 of 52) never get the page into the 30 candidates at all, and for another 14 the reranker pushes a candidate that was in the pool out of the top 5.
2. **Tables are the biggest problem.** Top-5 recall is 4 of 18 (22 percent) when the evidence is a table and 21 of 34 (62 percent) when it is text. The reranker helps on text (R@5 0.53 to 0.62) and **hurts on tables** (MRR 0.246 down to 0.156): it was trained on prose and scores flattened number runs poorly.
3. **Hybrid search did not help on this dataset.** Pool recall is the same or slightly lower than vector alone (single 0.75 against 0.77; shared 0.65 against 0.65), and the final numbers are within noise. It looks slightly better on text and slightly worse on tables. The CBG case that motivated it was a real fix, but one case is not a trend: on these long, instruction-laden questions BM25 alone is weak (R@30 0.58 single, 0.38 shared), and with equal-weight merging it adds noise as often as signal.
4. **Searching several documents is clearly harder** (R@5 0.33 against 0.48). Many questions name a company ("for AES") but nothing in the pages does, so the right company's pages do not reliably win.
5. **The dataset itself is hard for retrieval**, so absolute numbers are low for any system. Many questions ask for a ratio or a judgement ("does AMD have a healthy quick ratio?") whose evidence is the balance sheet or income statement, pages that never contain the words of the question; and many questions carry long boilerplate ("if this metric is not relevant, say so and explain"), which dilutes both the vector and the keyword query. Read these numbers as relative (between configurations) more than as absolute.

### Caveats

- 52 questions from 12 US filings; one run; chunk size 300 only. No confidence intervals.
- A hit means the right **page** is among the first k chunks, not that the chunk contains the answer. Pages can hold ten chunks, so this is generous at k=5 and k=10.
- Questions were not filtered for answerability by retrieval alone (some need several pages).

### Experiment 1: keeping the table grid (negative result)

Hypothesis: flattened tables (columns lost) are why table questions fail. Test: `--extractor plumber` rebuilds each page's text with `pdfplumber` word positions, grouping words into rows and marking column gaps with ` | ` (`Total revenues | 66,608 | 62,286 | 58,158`, header row kept). On borderless statements it recovered the grid cleanly in a manual check (American Express balance sheet, Boeing income statement). Same 12 documents, same questions, chunks 300/50:

| single scope | table R@5 | table R@30 | table MRR | text R@5 | all R@5 |
|---|---|---|---|---|---|
| hybrid + rerank, pypdf (baseline) | 0.22 | 0.50 | 0.135 | 0.62 | 0.48 |
| hybrid + rerank, grid kept | 0.22 | 0.44 | 0.127 | 0.59 | 0.46 |
| vector only, pypdf | 0.28 | 0.61 | 0.246 | 0.53 | 0.44 |
| vector only, grid kept | 0.28 | 0.44 | 0.256 | 0.56 | 0.46 |

**No improvement** (table candidate recall fell slightly; everything else is within noise). Keeping the grid is not what limits these questions.

Why, from reading the 18 table questions against their evidence pages: for most of them **the evidence page shares almost no words with the question.** "Quick ratio", "liquidity profile", "gross margin", "operating margin", "largest liability", "capital-intensive" are concepts the question names and the page never does; the page is a balance sheet or income statement whose rows are "Total current assets", "Cost of sales" and so on. The company name is often not on the page either ("American Express" does not appear on its balance sheet page). For 6 of the 18 table questions the evidence page contains none of the question's content words, and for most of the rest only generic ones ("income", "segment", "gross", the company name). So the failure is a **vocabulary gap between a question about a concept and a page of line items**, which a better table layout cannot close. Flattening exists and may still matter for answering from a retrieved table, but it is not the main retrieval problem on this dataset.

### Experiment 2: metadata and headings, no query rewriting (positive for several documents)

Motivated by the vocabulary-gap finding, with the constraint of no LLM and no hand-written word lists. Three changes, measured in two steps on the same 52 questions:

- **Step A (query time, no re-embedding):** the keyword search also sees each chunk's header (title and section); and when the question names some of the documents searched (matched against titles and file names, `docqa/docmatch.py`), a second vector and keyword search runs inside just those documents and joins the merge.
- **Step B (ingest time, all 12 documents re-embedded):** a heading detected from the page layout is added to each chunk's section (first short bold, larger or all-capital lines at the top of the page, skipping lines repeated on many pages); and PDF titles that are only filing numbers (`0000764478-23-000041`, the case for 6 of the 12 documents) fall back to the file name. Before this, the embedding header of those documents carried a meaningless number.

Hybrid + rerank (the current system), R@k and MRR:

| scope, group | baseline | A | B |
|---|---|---|---|
| shared, all (R@5 / R@30 / MRR) | 0.33 / 0.65 / 0.274 | 0.35 / 0.71 / 0.284 | **0.44 / 0.77 / 0.348** |
| shared, table evidence (R@5) | 0.11 | 0.11 | **0.28** |
| shared, text evidence (R@5) | 0.44 | 0.47 | **0.53** |
| single, all (R@5 / R@30 / MRR) | 0.48 / 0.75 / 0.337 | 0.48 / 0.75 / 0.347 | 0.50 / 0.71 / 0.374 |
| single, text (R@5 / MRR) | 0.62 / 0.444 | 0.62 / 0.459 | 0.65 / 0.502 |
| single, table (R@5 / R@10) | 0.22 / 0.39 | 0.22 / 0.39 | 0.22 / **0.22** |

Reading it:

- **Searching several documents improved clearly**: top-5 recall 0.33 to 0.44 (about six more questions of 52), candidate recall 0.65 to 0.77. Step A alone gave a small gain; most of it came from step B, i.e. from titles that now name the company and from headings in the header. This is a real fix for the multi-report case, and it needed no LLM.
- **One document: roughly flat**, with a better ranking on text (MRR 0.444 to 0.502) but **no help, and possibly harm, on tables** (single-document table R@10 0.39 to 0.22; vector-only table R@5 0.28 to 0.17). With 18 table questions that is two to three questions, so it may be noise, but there is no sign of a table gain from headings on their own.
- **The concept gap is untouched**: questions that name a concept the page never mentions ("quick ratio") still miss. Headings help only where the question names the statement or section.
- The two query-time features are now **on by default** (`retrieve(..., bm25_header=True, name_boost=True)`).

Heading detection quality (AMD 10-K): `Advanced Micro Devices, Inc. - Consolidated Balance Sheets` and similar on statement pages, sensible labels on most text pages, none on 32 of 121 pages, and some noise (a bold table row taken as a heading). Abbreviations that are not in the title ("AMEX", "J&J") do not trigger the name search.

Product bugs found along the way, all fixed with tests: owner-locked PDFs rejected; NUL bytes crashing ingestion (twice: in page text, then in the new heading text); filing numbers used as titles.

### What to do next

- Read the per-question misses (`per_question.csv`) to separate "retrieval failed" from "the question cannot be answered from one page".
- Try chunk sizes 200 and 500 (about 15 minutes each).
- Strip the boilerplate from questions before searching (a cheap test of whether it matters).
- Close the concept-to-table vocabulary gap (this is now the main lead for table questions): tag statement pages by their title (income statement, balance sheet, cash flow) and add the vocabulary people ask about (gross margin, operating margin, liquidity, quick ratio, liabilities, capital expenditure), either as fixed lists or written by an LLM; or expand the question with an LLM before searching (privacy and quota cost). Also test bypassing the reranker for number-heavy chunks, since it lowers table scores.
- Try other merge weights than equal-rank fusion, and a larger pool.

## 13. Log: what got stuck, what fixed it, and what it changed

A running record, oldest first. Add an entry for every experiment or problem, with the numbers, so the reasons behind each change stay findable. "Hybrid + rerank" is the current system; R@5 = share of questions with the evidence page in the top 5 chunks; MRR as defined above. 52 questions, 12 documents, chunks 300/50, unless stated.

### Scorecard

| Stage | One document: R@5 / MRR | All 12 documents: R@5 / MRR | Table evidence, one doc / all docs (R@5) |
|---|---|---|---|
| Baseline (pypdf text, hybrid + rerank) | 0.48 / 0.337 | 0.33 / 0.274 | 0.22 / 0.11 |
| Table grid kept (`pdfplumber`) | 0.46 / 0.319 | 0.33 / 0.250 | 0.22 / 0.17 |
| + title in keyword search, search inside named documents (step A) | 0.48 / 0.347 | 0.35 / 0.284 | 0.22 / 0.11 |
| + layout headings, filing-number titles replaced by file names (step B, current) | **0.50 / 0.374** | **0.44 / 0.348** | 0.22 / **0.28** |

With LLM question expansion and reranking against the expansion (entry 13, descriptions written by Claude, not Gemini): one document **0.87 / 0.665**, all documents **0.83 / 0.627**.

Ceiling with a perfect query (oracle, entry 12): one document 1.00 / 0.952, all documents 1.00 / 0.925.

Candidate recall (R@30, how often the reranker even sees the page): all documents 0.65, 0.63, 0.71, **0.77**; one document 0.75, 0.69, 0.75, 0.71.

### Entries

**0. Before the evaluation: the CBG miss (manual test on the Reliance report).**
- *Stuck:* "What percentage of India's CBG production does RIL contribute to?" returned "not found" although page 15 says "over 30%".
- *Diagnosis:* the vector search ranked the answer chunk 145th (similarity 0.800; the 30th was 0.822), below tables of subsidiary names, so the reranker never saw it. Embedded alone, the sentence scored 0.893 against the question; the reranker given the chunk ranked it 4th of 300. A mixed 200-word chunk dilutes one sentence in a single vector.
- *Fix:* hybrid search (BM25 keyword search merged with the vector search by reciprocal rank fusion).
- *Result:* on that one question, the answer chunk moved from list position 30 (at 300-word chunks) to 1 and was reranked first. One question is not a trend; see entry 4.

**1. Choosing the data.** FinanceBench (150 questions, evidence pages, public PDFs) fits long financial reports. *Stuck:* no licence file in its repository. *Handled:* data lives in a folder outside the repository, is never committed, and is used for internal evaluation only.

**2. First smoke test: a PDF rejected as "password protected".**
- *Diagnosis:* the Best Buy 10-Q is locked only with an owner password and opens with an empty one; the extractor rejected every encrypted file without trying that.
- *Fix:* try the empty password first (test added). *Result:* the file ingests; this affects many real filings.

**3. Second smoke test: ingestion crashed on NUL bytes.**
- *Diagnosis:* checkbox glyphs in a 10-Q extracted as `\x00`, which Postgres text columns refuse; the app would have shown a generic "something went wrong".
- *Fix:* replace NUL with a space (test added). *Result:* ingests. (It came back once more, through heading text, in entry 10; see there.)

**4. Baseline run and what it said.** About half the questions have the evidence page in the top 5 in one document (0.48), a third across documents (0.33); 13 of 52 never reach the 30 candidates; tables 4 of 18 (22 percent) against text 21 of 34 (62 percent); the reranker helps on text and hurts on tables; hybrid search made no clear difference here (candidate recall 0.75 against 0.77 for vector alone). Dataset page numbers are 0-based (all 64 evidence items located by text). Ingestion ran about twice as fast as estimated (4,800 chunks in 14 minutes).

**5. Hypothesis: flat tables cause the table misses.**
- *Test:* rebuild each page's grid with `pdfplumber` word positions (` | ` between columns) and rerun everything.
- *Result:* no gain (table R@5 0.22 unchanged, table candidate recall 0.50 to 0.44, overall slightly worse). It was dropped as a retrieval fix; it may still help answer quality, which is not measured yet. The experimental extractor stays in `backend/evals/`.
- *Diagnosis, from reading the 18 table questions against their pages:* a **vocabulary gap**. Questions name concepts ("quick ratio", "gross margin", "liquidity profile", "capital-intensive") that the statement page never mentions; for 6 of 18 the page has none of the question's content words, and the company name is often not on the page. I had told you flat tables were the main cause; this experiment showed they are not, for retrieval.

**6. Which fix? Ideas weighed.**
- *A fixed finance word list* (tag balance sheet pages with "liquidity, quick ratio, ..."): rejected, because it only works for finance and needs a new list per domain.
- *Synonyms in BM25:* would not close it. "Quick ratio" is computed from the page's rows, not a synonym of them; that takes reasoning or a trained model.
- *LLM question rewriting:* works in any domain but costs a call per question and sends the question to Google; set aside because the aim is to minimise LLM calls.
- *Chosen:* metadata filtering and boosting, and section or heading tags on chunks (no LLM, no word lists), measured before building more. Rule-based query expansion (including boilerplate stripping) was deliberately left out.
- *Caveat noted:* the page-level hit is strict. For several "missed" questions the top results were topical MD&A pages (3M liquidity discussion, Amcor performance), just not the labelled statement page. An answer-level evaluation is still needed.

**7. Step A (query time): keyword search sees the title; search inside documents the question names.** *Stuck:* the first run gave shared-scope vector numbers identical to the baseline, so the name matching was not firing. *Diagnosis:* many PDF titles are filing numbers (`0000004962-23-000006`, `0000764478-23-000041`), so matching on the title never worked. *Fix:* match on title and file name. *Result:* small gain, mostly in several-document search (candidate recall 0.65 to 0.71, R@5 0.33 to 0.35).

**8. The filing-number titles were also a product bug.** The embedding header (`title | section`) of 6 of the 12 documents carried a meaningless number, so the header could not name the company. *Fix:* a title with fewer than 40 percent letters is discarded and the file name is used (tests added). This needs re-embedding, so it went into step B.

**9. Step B (ingest time): layout-based headings.** Detected from font size, boldness and capitals at the top of the page, skipping lines that repeat on many pages and lines that are mostly numbers or dates (no word lists). On the AMD 10-K: `Advanced Micro Devices, Inc. - Consolidated Balance Sheets`, `... - Notes to Consolidated Financial Statements`; none found on 32 of 121 pages; some noise (a bold table row taken as a heading).

**10. Step B run: crashed again on NUL bytes.** The new heading text carried `\x00`; fixed at the source and tested (the crash cost one restart of the run).

**11. Step B result.** All 12 documents: R@5 0.33 to **0.44**, candidate recall 0.65 to **0.77**, MRR 0.274 to **0.348**; table questions across documents R@5 0.11 to **0.28**; text 0.44 to 0.53. One document: R@5 0.48 to 0.50, MRR 0.337 to 0.374 (text 0.444 to 0.502), but **table R@10 fell 0.39 to 0.22** and vector-only table R@5 0.28 to 0.17 (two to three questions of 18; possibly noise, no sign of a table gain). Most of the gain came from the ingest-side changes (titles now name the company, headings in the header), not from the name matching alone. The query-time features were switched on by default.

**12. Ceiling test (oracle query).** *Question:* with perfect understanding of the question, how well could the current index do? *Test:* `--oracle` searches with the first 300 words of the evidence text instead of the question, everything else unchanged (current system, same 12 documents). It is deliberately a leak: the query is the page's own text, so this measures whether each page can be found at all, not how good the system is.

| Hybrid + rerank | R@1 | R@5 | R@30 | MRR |
|---|---|---|---|---|
| one document, real question | 0.25 | 0.50 | 0.71 | 0.374 |
| one document, **oracle** | 0.90 | **1.00** | 1.00 | 0.952 |
| all 12 documents, real question | 0.23 | 0.44 | 0.77 | 0.348 |
| all 12 documents, **oracle** | 0.87 | **1.00** | 1.00 | 0.925 |

Also for the oracle: table evidence 1.00 at R@5 in both scopes (0.28 to 1.00 across documents), vector alone 0.96 (one document) and 0.85 (all documents) at R@5, keyword alone 1.00.

*Reading:* the extraction, chunking, cleaning, headers, index and reranker are **not** what limits retrieval on this dataset. Every evidence page, tables included, is found in the top 5 when the query matches it, so the ceiling for this measure is close to 100 percent and the whole gap (0.50 and 0.44 against 1.00) is the distance between how a question is worded and how the page is worded. That settles the earlier doubt about the table results: tables are retrievable; table questions fail because their wording does not match the page. Caveats: the oracle is an easy test (exact text overlap), so 1.00 shows the pages are reachable, not that a human question will reach them; and it does not measure whether an answer can be read from the page.

**13. LLM question expansion (the biggest gain so far).**
- *Idea:* since the gap is the question's wording (entry 12), let an LLM write, for each question, a short description of the page that would answer it (statement titles, line-item names, standard terms), and search with the question plus that description. The prompt is generic (nothing about finance) and tells the model not to answer or guess numbers.
- *First attempt stuck:* Gemini returned a 503 ("high demand") on the first call, and our client gave up on the first 503. *Fix:* retry 500, 502, 503 and 504 with 3, 6, 12 and 24 second waits (three tests). That helps the app as well.
- *Who wrote the descriptions:* the harness could not run without your Gemini key (it lives only in your terminal), so for this experiment **a Claude subagent wrote all 52** (`expansions_claude.json`), given the question text only: no evidence, no results, no tools except the final file write. Not Gemini. Where the cache is complete the harness needs no key. A Gemini version can be run with `--expand --expansions-file expansions_gemini.json`.
- *Run A:* search with question + description, rerank against the original question.
- *Run B:* same search, rerank against the question + description (`--rerank-expanded`). I tried B after seeing that A's reranker threw away pages that retrieval had found; two variants on the same 52 questions, so a small selection effect is possible.

| Hybrid + rerank | one document: R@1 / R@5 / R@30 / MRR | all 12 documents: R@1 / R@5 / R@30 / MRR |
|---|---|---|
| before (current, entry 11) | 0.25 / 0.50 / 0.71 / 0.374 | 0.23 / 0.44 / 0.77 / 0.348 |
| A: expand, rerank vs question | 0.27 / 0.58 / 0.98 / 0.421 | 0.23 / 0.54 / 0.96 / 0.380 |
| **B: expand, rerank vs expanded** | **0.54 / 0.87 / 0.98 / 0.665** | **0.50 / 0.83 / 0.96 / 0.627** |
| oracle ceiling (entry 12) | 0.90 / 1.00 / 1.00 / 0.952 | 0.87 / 1.00 / 1.00 / 0.925 |

- **Table evidence (B):** R@5 0.22 to **0.83** in one document, 0.28 to **0.83** across documents. Text evidence: 0.65 to 0.88 and 0.53 to 0.82.
- **Candidate recall** (does the page reach the reranker at all): one document 0.71 to 0.98, all documents 0.77 to 0.96; for tables 0.39 to 0.94.
- **Before reranking** the merged list already reaches R@5 0.79 (one document) and 0.81 (all documents), against 0.50 and 0.42 before. Reranking against the *original* question then lowers it to 0.58 and 0.54 (A): the reranker, scoring the bare question against statement pages, demotes the right ones. Scoring against the description repairs that (B). This agrees with the earlier finding that the reranker hurts on tables.
- *Reading:* the question-to-page wording gap was the dominant problem, and an LLM that knows what such a page looks like closes most of it: about 87 percent of the way to the ceiling at top 5 for one document, 83 percent for several, without any word list in our code.

*Caveats, important:*
- The descriptions came from a strong model that knows how financial filings are laid out. A free Gemini model may do worse; **run it with Gemini before deciding anything** (the harness supports it).
- Cost in the product: one extra LLM call per question (before the answer call), added latency, and the question text goes to Google. It would have to be an opt-in setting like answer generation.
- 52 questions, one run per variant, chunk size 300. The rerank variant was chosen after seeing the first result.
- Questions were not seen by the writer together with their evidence, but the writer is a general model with background knowledge of public companies and filings (for example it wrote the 3M Q2 date). That is the same advantage a hosted LLM would have in the product, so it is a fair estimate of the idea, not of a specific model.

### Open problems (as of this log)

1. **Question-to-page wording gap** (largely closed by LLM expansion in entry 13, but only measured with Claude-written descriptions and costing one LLM call per question). Concept questions ("quick ratio", "gross margin") miss when the page never names the concept. Needs something that links a concept to its statement: an LLM (rewrite the question, or describe each table or page at upload), a user glossary, or accepting the topical MD&A pages.
2. **Table questions in a single document** did not improve and may have got slightly worse; the reranker is known to score numeric chunks poorly.
3. **No answer-level evaluation.** Page hits undercount useful retrievals and say nothing about whether the answer is right or the numbers are read correctly (where flat tables would matter).
4. **Small sample:** 52 questions, one run per setting, one chunk size. Chunk sizes 200 and 500 and the merge weights are untested.
5. **Heading detection** misses about a quarter of pages and sometimes picks a table row; abbreviations ("AMEX") do not trigger the name search.
