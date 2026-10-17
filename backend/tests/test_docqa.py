import hashlib
import io
import os

import pytest
from fastapi.testclient import TestClient

TEST_DB = os.environ.get("DOCQA_TEST_DATABASE_URL", "postgresql://localhost/docqa_test")


def _vec(text: str) -> list[float]:
    """Deterministic fake embedding: one dimension per word hash, so shared words mean similarity."""
    v = [0.0] * 768
    for w in text.lower().split():
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 768] += 1.0
    return v


def _pdf(pages: list[str], bookmarks: dict[int, tuple[str, int]] | None = None, title: str | None = None) -> bytes:
    """bookmarks: page index -> (title, level)."""
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    if title:
        c.setTitle(title)
        c.setAuthor("Test Author")
    for i, text in enumerate(pages):
        if bookmarks and i in bookmarks:
            name, level = bookmarks[i]
            c.bookmarkPage(f"p{i}")
            c.addOutlineEntry(name, f"p{i}", level=level)
        c.drawString(72, 750, text)
        c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCQA_DATABASE_URL", TEST_DB)
    monkeypatch.setenv("DOCQA_STORAGE_DIR", str(tmp_path / "files"))
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.setenv("DOCQA_MIN_RERANK_SCORE", "off")
    from docqa import db, providers
    db.reset()
    try:
        db.init_db()
    except Exception as e:  # no local Postgres with pgvector
        pytest.skip(f"Postgres with pgvector not available: {e}")
    from sqlalchemy import text
    with db.engine().begin() as conn:
        conn.execute(text("TRUNCATE chunks, documents RESTART IDENTITY CASCADE"))
    monkeypatch.setattr(providers, "embed", lambda texts, query: [_vec(t) for t in texts])
    monkeypatch.setattr(providers, "generate", lambda system, prompt, model=None: "Answer [1]")
    from docqa import rerank
    # Fake reranker: score = how many question words the passage contains.
    monkeypatch.setattr(rerank, "rerank", lambda q, texts: [float(len(set(q.lower().split()) & set(t.lower().split())))
                                                              for t in texts])

    from alphabacktest.api import app
    with TestClient(app) as c:
        yield c
    db.reset()


def upload(client, name="a.pdf", pages=("hello world this is a test document",), data=None):
    return client.post("/api/docqa/documents", files={"file": (name, data or _pdf(list(pages)), "application/pdf")})


def test_upload_processes_and_lists(client):
    r = upload(client, pages=["revenue grew twelve percent", "debt repayment schedule"])
    assert r.status_code == 202
    docs = client.get("/api/docqa/documents").json()
    assert docs[0]["status"] == "ready" and docs[0]["pageCount"] == 2 and docs[0]["chunkCount"] == 2


def test_ask_returns_ranked_chunks_with_page(client):
    upload(client, pages=["the cat sat on the mat", "quarterly revenue grew twelve percent", "unrelated gardening notes"])
    out = client.post("/api/docqa/ask", json={"question": "how much did revenue grow", "generate": True}).json()
    assert out["answer"] == "Answer [1]"
    assert out["chunks"][0]["page"] == 2
    scores = [c["vectorScore"] for c in out["candidates"]]
    assert scores == sorted(scores, reverse=True)
    assert [c["vectorRank"] for c in out["candidates"]] == [1, 2, 3]


def test_rerank_reorders_candidates(client, monkeypatch):
    from docqa import rerank
    upload(client, pages=["alpha beta gamma delta notes", "alpha unrelated filler words here", "zeta eta theta iota kappa"])
    # The reranker prefers the third page even though vectors prefer the first.
    monkeypatch.setattr(rerank, "rerank", lambda q, texts: [1.0 if "zeta" in t else 0.0 for t in texts])
    out = client.post("/api/docqa/ask", json={"question": "alpha beta", "topK": 2}).json()
    assert out["candidates"][0]["page"] == 1 and out["candidates"][0]["vectorRank"] == 1
    assert out["chunks"][0]["page"] == 3
    assert out["chunks"][0]["rerankRank"] == 1 and out["chunks"][0]["vectorRank"] == 3
    assert len(out["chunks"]) == 2 and len(out["candidates"]) == 3


def test_min_score_drops_weak_results(client, monkeypatch):
    from docqa import rerank
    upload(client, pages=["alpha beta gamma delta notes", "alpha unrelated filler words here", "zeta eta theta iota kappa"])
    monkeypatch.setattr(rerank, "rerank", lambda q, texts: [2.0 if "zeta" in t else -3.0 for t in texts])
    out = client.post("/api/docqa/ask", json={"question": "zeta", "minScore": 0}).json()
    assert [c["page"] for c in out["chunks"]] == [3]
    assert out["droppedBelowCutoff"] == 2 and out["minScore"] == 0 and len(out["candidates"]) == 3
    none = client.post("/api/docqa/ask", json={"question": "zeta", "minScore": 5}).json()
    assert none["chunks"] == [] and none["droppedBelowCutoff"] == 3
    off = client.post("/api/docqa/ask", json={"question": "zeta", "minScore": None}).json()
    assert len(off["chunks"]) == 3 and off["droppedBelowCutoff"] == 0 and off["minScore"] is None


def test_built_in_default_cutoff_and_user_override(client, monkeypatch):
    from docqa import rerank
    upload(client, pages=["alpha beta gamma delta notes", "zeta eta theta iota kappa"])
    monkeypatch.setattr(rerank, "rerank", lambda q, texts: [2.0 if "zeta" in t else -3.0 for t in texts])
    monkeypatch.delenv("DOCQA_MIN_RERANK_SCORE")
    assert client.get("/api/docqa/config").json()["minScore"] == -2.5
    default = client.post("/api/docqa/ask", json={"question": "zeta"}).json()
    assert [c["page"] for c in default["chunks"]] == [2] and default["minScore"] == -2.5
    everything = client.post("/api/docqa/ask", json={"question": "zeta", "minScore": None}).json()
    assert len(everything["chunks"]) == 2
    stricter = client.post("/api/docqa/ask", json={"question": "zeta", "minScore": 5}).json()
    assert stricter["chunks"] == []


def test_min_score_from_environment(client, monkeypatch):
    from docqa import rerank
    upload(client, pages=["alpha beta gamma delta notes", "zeta eta theta iota kappa"])
    monkeypatch.setattr(rerank, "rerank", lambda q, texts: [2.0 if "zeta" in t else -3.0 for t in texts])
    monkeypatch.setenv("DOCQA_MIN_RERANK_SCORE", "0")
    out = client.post("/api/docqa/ask", json={"question": "zeta"}).json()
    assert [c["page"] for c in out["chunks"]] == [2]


def test_number_of_final_results_is_chosen_per_question(client):
    upload(client, data=_long_pdf())   # 3 chunks at the default size
    upload(client, pages=["alpha one text here for testing", "beta two text here for testing", "gamma three text here for testing"])
    five = client.post("/api/docqa/ask", json={"question": "text"}).json()
    assert len(five["chunks"]) == 5 and len(five["candidates"]) == 6
    two = client.post("/api/docqa/ask", json={"question": "text", "topK": 2}).json()
    assert len(two["chunks"]) == 2 and len(two["candidates"]) == 6
    assert client.post("/api/docqa/ask", json={"question": "text", "topK": 0}).status_code == 422
    assert client.post("/api/docqa/ask", json={"question": "text", "topK": 21}).status_code == 422
    c = client.get("/api/docqa/config").json()
    assert (c["topK"], c["maxTopK"]) == (5, 20)


def test_rerank_can_be_turned_off(client):
    upload(client, pages=["alpha section of the report", "beta section of the report"])
    out = client.post("/api/docqa/ask", json={"question": "alpha", "rerank": False}).json()
    assert out["chunks"][0]["rerankRank"] is None and out["chunks"][0]["vectorRank"] == 1


def test_ask_without_generation_and_top_k(client):
    upload(client, pages=["alpha section of the report", "beta section of the report", "gamma section of the report"])
    out = client.post("/api/docqa/ask", json={"question": "alpha", "topK": 2}).json()
    assert out["answer"] is None and len(out["chunks"]) == 2 and len(out["candidates"]) == 3


def test_ask_limited_to_selected_documents(client):
    a = upload(client, "a.pdf", ["apples and oranges are fruit sold here"]).json()["id"]
    upload(client, "b.pdf", ["apples and bananas are fruit sold here"])
    out = client.post("/api/docqa/ask", json={"question": "apples", "documentIds": [a]}).json()
    assert {c["documentId"] for c in out["chunks"]} == {a}


def test_delete_removes_document_and_chunks(client):
    doc = upload(client).json()["id"]
    assert client.delete(f"/api/docqa/documents/{doc}").status_code == 204
    assert client.get("/api/docqa/documents").json() == []
    assert client.post("/api/docqa/ask", json={"question": "hello"}).json()["chunks"] == []
    assert client.delete(f"/api/docqa/documents/{doc}").status_code == 404


def test_rejects_non_pdf(client):
    assert upload(client, "a.txt", data=b"hello").status_code == 400
    assert upload(client, "a.pdf", data=b"not a pdf at all").status_code == 400


def test_unreadable_pdf_is_marked_failed(client):
    upload(client, pages=[""])  # a page with no text, like a scan
    doc = client.get("/api/docqa/documents").json()[0]
    assert doc["status"] == "failed" and "readable text" in doc["error"]


def test_stores_model_chunk_settings_hash_and_pdf_metadata(client):
    data = _pdf(["a page with enough readable text in it"], title="Annual Report 2025")
    r = upload(client, data=data).json()
    doc = client.get("/api/docqa/documents").json()[0]
    assert doc["embeddingModel"] == "jinaai/jina-embeddings-v2-base-en | title+section+clean+heading"
    assert (doc["chunkWords"], doc["chunkOverlap"]) == (300, 50)
    assert doc["pdfTitle"] == "Annual Report 2025" and doc["pdfAuthor"] == "Test Author"
    assert doc["stale"] is False and r["id"] == doc["id"]
    import hashlib
    from docqa import db
    from docqa.models import Document
    with db.session() as s:
        assert s.get(Document, doc["id"]).file_hash == hashlib.sha256(data).hexdigest()


def test_duplicate_upload_is_refused(client):
    data = _pdf(["the same file uploaded twice for testing"])
    assert upload(client, "a.pdf", data=data).status_code == 202
    again = upload(client, "b.pdf", data=data)
    assert again.status_code == 409 and again.json()["detail"]["error"] == "duplicate"
    assert len(client.get("/api/docqa/documents").json()) == 1


def test_failed_copy_of_same_file_is_replaced(client):
    data = _pdf([""])   # unreadable, so it fails
    upload(client, data=data)
    assert client.get("/api/docqa/documents").json()[0]["status"] == "failed"
    assert upload(client, data=data).status_code == 202
    assert len(client.get("/api/docqa/documents").json()) == 1


def test_sections_come_from_bookmarks(client):
    pages = ["intro text for the report goes here", "risk factors discussion about suppliers", "more detail on supplier risk", "financial results and revenue growth"]
    marks = {0: ("Overview", 0), 1: ("Risk Factors", 0), 2: ("Suppliers", 1), 3: ("Financials", 0)}
    upload(client, data=_pdf(pages, marks))
    out = client.post("/api/docqa/ask", json={"question": "supplier risk", "topK": 5, "minScore": None}).json()
    by_page = {c["page"]: c["section"] for c in out["candidates"]}
    assert by_page == {1: "Overview", 2: "Risk Factors", 3: "Risk Factors > Suppliers", 4: "Financials"}


def test_no_bookmarks_means_no_section(client):
    upload(client, pages=["a page with enough readable text in it"])
    out = client.post("/api/docqa/ask", json={"question": "page"}).json()
    assert out["candidates"][0]["section"] is None


def test_documents_from_another_embedding_model_are_stale_and_skipped(client, monkeypatch):
    data = _pdf(["a page with enough readable text in it"])
    upload(client, data=data)
    monkeypatch.setenv("DOCQA_LOCAL_EMBEDDING_MODEL", "some/other-model")
    doc = client.get("/api/docqa/documents").json()[0]
    assert doc["stale"] is True
    assert client.post("/api/docqa/ask", json={"question": "page"}).json()["candidates"] == []
    # uploading the same file again replaces the stale copy
    again = upload(client, data=data)
    assert again.status_code == 202 and len(client.get("/api/docqa/documents").json()) == 1


def test_models_see_title_and_section_but_stored_text_is_unchanged(client, monkeypatch):
    from docqa import providers, rerank
    seen = {"embed": [], "rerank": []}
    monkeypatch.setattr(providers, "embed", lambda texts, query: seen["embed"].extend(texts) or [_vec(t) for t in texts])
    monkeypatch.setattr(rerank, "rerank", lambda q, texts: seen["rerank"].extend(texts) or [0.0] * len(texts))
    pages = ["revenue grew twelve percent this year", "supplier risk is concentrated in one country"]
    upload(client, data=_pdf(pages, {0: ("Financials", 0), 1: ("Risk Factors", 0)}, title="Annual Report 2025"))
    assert seen["embed"][0].startswith("Annual Report 2025 | Financials\n\n")
    assert seen["embed"][1].startswith("Annual Report 2025 | Risk Factors\n\n")
    out = client.post("/api/docqa/ask", json={"question": "supplier risk"}).json()
    assert all(t.startswith("Annual Report 2025 | ") for t in seen["rerank"])
    assert all(not c["text"].startswith("Annual Report") for c in out["candidates"])   # shown text is the PDF's own


def test_header_falls_back_to_file_name_and_skips_missing_parts(client, monkeypatch):
    from docqa import providers
    seen = []
    monkeypatch.setattr(providers, "embed", lambda texts, query: seen.extend(texts) or [_vec(t) for t in texts])
    upload(client, "Quarterly Letter.pdf", pages=["a page with enough readable text in it"])
    assert seen[0].startswith("Quarterly Letter\n\n")


def _long_pdf():
    return _pdf([" ".join(f"word{i}" for i in range(600))])


def upload_with(client, data, **form):
    return client.post("/api/docqa/documents", files={"file": ("a.pdf", data, "application/pdf")}, data=form)


def test_chunk_size_and_overlap_are_chosen_per_upload(client):
    data = _long_pdf()
    assert upload_with(client, data, chunkWords="100", chunkOverlap="0").status_code == 202
    doc = client.get("/api/docqa/documents").json()[0]
    assert (doc["chunkWords"], doc["chunkOverlap"], doc["chunkCount"]) == (100, 0, 6)


def test_defaults_apply_when_not_chosen(client):
    upload(client, data=_long_pdf())
    doc = client.get("/api/docqa/documents").json()[0]
    assert (doc["chunkWords"], doc["chunkOverlap"]) == (300, 50) and doc["chunkCount"] == 3


@pytest.mark.parametrize("form, code", [
    ({"chunkWords": "50"}, "bad_chunk_size"), ({"chunkWords": "5000"}, "bad_chunk_size"),
    ({"chunkWords": "200", "chunkOverlap": "150"}, "bad_overlap"), ({"chunkOverlap": "-1"}, "bad_overlap"),
])
def test_bad_chunk_settings_are_rejected(client, form, code):
    r = upload_with(client, _long_pdf(), **form)
    assert r.status_code == 400 and r.json()["detail"]["error"] == code


def test_same_file_with_other_chunk_settings_replaces_the_old_copy(client):
    data = _long_pdf()
    upload_with(client, data, chunkWords="300", chunkOverlap="50")
    assert upload_with(client, data, chunkWords="300", chunkOverlap="50").status_code == 409
    assert upload_with(client, data, chunkWords="150", chunkOverlap="25").status_code == 202
    docs = client.get("/api/docqa/documents").json()
    assert len(docs) == 1 and docs[0]["chunkWords"] == 150


def test_config_reports_chunk_defaults_and_limits(client):
    c = client.get("/api/docqa/config").json()
    assert (c["chunkWords"], c["chunkOverlap"], c["minChunkWords"], c["maxChunkWords"]) == (300, 50, 100, 800)


def test_other_users_documents_are_invisible(client, monkeypatch):
    upload(client)
    from alphabacktest import auth
    from types import SimpleNamespace
    from alphabacktest.api import app
    app.dependency_overrides[auth.current_user] = lambda: SimpleNamespace(id=999)
    try:
        assert client.get("/api/docqa/documents").json() == []
        assert client.post("/api/docqa/ask", json={"question": "hello"}).json()["chunks"] == []
        assert client.delete("/api/docqa/documents/1").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_disabled_without_database_url(monkeypatch):
    monkeypatch.delenv("DOCQA_DATABASE_URL", raising=False)
    from alphabacktest.api import app
    with TestClient(app) as c:
        assert c.get("/api/docqa/config").json()["enabled"] is False
        assert c.get("/api/docqa/documents").status_code == 503


def test_chunking_keeps_pages_and_overlaps():
    from docqa.chunking import chunk_pages
    words = " ".join(f"w{i}" for i in range(500))
    chunks = chunk_pages([words, "short page"], size=200, overlap=50)
    assert [p for p, _ in chunks] == [1, 1, 1, 2]
    assert chunks[0][1].split()[150:] == chunks[1][1].split()[:50]


def test_generation_failure_still_returns_passages(client, monkeypatch):
    from docqa import providers

    def boom(system, prompt, model=None):
        raise providers.ProviderError("Gemini is rate limited.")
    monkeypatch.setattr(providers, "generate", boom)
    upload(client, pages=["quarterly revenue grew twelve percent"])
    r = client.post("/api/docqa/ask", json={"question": "revenue", "generate": True})
    out = r.json()
    assert r.status_code == 200 and out["answer"] is None
    assert out["answerError"] == "Gemini is rate limited." and len(out["chunks"]) == 1


def test_generation_skipped_when_nothing_passes_cutoff(client, monkeypatch):
    from docqa import providers
    calls = []
    monkeypatch.setattr(providers, "generate", lambda system, prompt, model=None: calls.append(1) or "x")
    upload(client, pages=["quarterly revenue grew twelve percent"])
    out = client.post("/api/docqa/ask", json={"question": "revenue", "generate": True, "minScore": 99}).json()
    assert out["chunks"] == [] and out["answer"] is None and out["answerError"] is None and calls == []


def test_hybrid_search_finds_exact_term_vector_search_misses(client):
    fillers = [f"revenue growth topic{w} percent production share market report" for w in "abcdef"]   # differ mid-line, so cleaning keeps them
    needle = "zyxq " + " ".join(f"unrelated{i}" for i in range(40))
    upload(client, pages=fillers + [needle])
    body = {"question": "production share zyxq", "candidates": 3, "topK": 3, "rerank": False}
    plain = client.post("/api/docqa/ask", json={**body, "hybrid": False}).json()
    assert 7 not in [c["page"] for c in plain["candidates"]]            # vector search alone misses the needle
    out = client.post("/api/docqa/ask", json=body).json()
    found = [c for c in out["candidates"] if c["page"] == 7]
    assert found and found[0]["vectorRank"] is None and found[0]["keywordRank"] == 1
    assert [c["rank"] for c in out["candidates"]] == [1, 2, 3]
    assert len(out["candidates"]) == 3 and all(c["vectorScore"] is not None for c in out["candidates"])


def test_hybrid_respects_selected_documents_and_user(client):
    a = upload(client, "a.pdf", ["zyxq appears only here in the first file"]).json()["id"]
    upload(client, "b.pdf", ["zyxq appears also in the second file"])
    out = client.post("/api/docqa/ask", json={"question": "zyxq", "documentIds": [a]}).json()
    assert {c["documentId"] for c in out["candidates"]} == {a}


def test_models_endpoint_and_chosen_model(client, monkeypatch):
    from docqa import providers
    monkeypatch.setattr(providers, "list_generation_models", lambda: [{"id": "gemini-a", "name": "A"}, {"id": "gemini-b", "name": "B"}])
    used = []
    monkeypatch.setattr(providers, "generate", lambda system, prompt, model=None: used.append(model) or "ok")
    listing = client.get("/api/docqa/models").json()
    assert [m["id"] for m in listing["models"]] == ["gemini-a", "gemini-b"] and listing["default"]
    upload(client, pages=["quarterly revenue grew twelve percent"])
    ask = lambda **kw: client.post("/api/docqa/ask", json={"question": "revenue", "generate": True, **kw})
    assert ask(model="gemini-b").json()["answer"] == "ok" and used == ["gemini-b"]
    assert ask().json()["answer"] == "ok" and used[-1] is None                      # no model: server default
    r = ask(model="../evil:generateContent")
    assert r.status_code == 400 and r.json()["detail"]["error"] == "bad_model"       # never put unlisted names in the URL
    assert len(used) == 2


def test_model_choice_ignored_without_generation(client, monkeypatch):
    from docqa import providers
    monkeypatch.setattr(providers, "list_generation_models", lambda: [])
    upload(client, pages=["quarterly revenue grew twelve percent"])
    r = client.post("/api/docqa/ask", json={"question": "revenue", "model": "anything"})
    assert r.status_code == 200 and r.json()["answer"] is None


def test_ask_rejects_empty_or_unsearchable_document_list(client):
    doc = upload(client, pages=["apples are fruit"]).json()["id"]
    empty = client.post("/api/docqa/ask", json={"question": "apples", "documentIds": []})
    assert empty.status_code == 400 and empty.json()["detail"]["error"] == "no_documents"
    gone = client.post("/api/docqa/ask", json={"question": "apples", "documentIds": [9999]})
    assert gone.status_code == 400 and gone.json()["detail"]["error"] == "no_searchable_documents"
    client.delete(f"/api/docqa/documents/{doc}")
    deleted = client.post("/api/docqa/ask", json={"question": "apples", "documentIds": [doc]})
    assert deleted.status_code == 400 and deleted.json()["detail"]["error"] == "no_searchable_documents"
    # leaving the field out still searches everything
    upload(client, "b.pdf", ["apples and pears are fruit"])
    assert client.post("/api/docqa/ask", json={"question": "apples"}).json()["candidates"]


def test_ask_ignores_unsearchable_ids_when_one_is_usable(client):
    a = upload(client, "a.pdf", ["apples are fruit sold here"]).json()["id"]
    out = client.post("/api/docqa/ask", json={"question": "apples", "documentIds": [a, 9999]}).json()
    assert {c["documentId"] for c in out["candidates"]} == {a}


def _encrypted_pdf(user_password: str) -> bytes:
    from reportlab.lib import pdfencrypt
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, encrypt=pdfencrypt.StandardEncryption(user_password, ownerPassword="owner-secret"))
    c.drawString(72, 750, "quarterly revenue grew twelve percent")
    c.showPage()
    c.save()
    return buf.getvalue()


def test_permission_locked_pdf_is_read_but_password_protected_is_rejected(client):
    ok = upload(client, "locked.pdf", data=_encrypted_pdf(""))      # owner password only: opens without a password
    assert ok.status_code == 202
    docs = {d["filename"]: d for d in client.get("/api/docqa/documents").json()}
    assert docs["locked.pdf"]["status"] == "ready" and docs["locked.pdf"]["chunkCount"] == 1
    upload(client, "secret.pdf", data=_encrypted_pdf("needs-a-password"))
    docs = {d["filename"]: d for d in client.get("/api/docqa/documents").json()}
    assert docs["secret.pdf"]["status"] == "failed" and "password" in docs["secret.pdf"]["error"]


def test_name_boost_searches_inside_the_documents_the_question_names(client):
    from docqa import db, pipeline
    filler = [f"topic{w} revenue growth percent production share market report" for w in "abcdefgh"]
    upload(client, "zeta_2022.pdf", filler)
    acme = upload(client, "acme_2022.pdf", ["revenue noted once among unrelated words about gardening and weather only here"]).json()["id"]
    with db.session() as s:
        plain = pipeline.retrieve(s, 1, "acme revenue growth", None, 3, hybrid=True, name_boost=False)
        named = pipeline.retrieve(s, 1, "acme revenue growth", None, 3, hybrid=True)   # on by default
    assert acme not in {h.document_id for h in plain}      # the other document crowds it out
    assert acme in {h.document_id for h in named}          # a search inside "acme" brings its chunk into the pool


def _make_stale(doc_id):
    from sqlalchemy import text

    from docqa import db
    with db.engine().begin() as conn:
        conn.execute(text("UPDATE documents SET embedding_model = 'old recipe' WHERE id = :i"), {"i": doc_id})


def test_reprocess_rebuilds_a_stale_document_from_the_stored_file(client):
    doc = upload(client, pages=["quarterly revenue grew twelve percent", "debt repayment schedule"]).json()["id"]
    _make_stale(doc)
    listed = {d["id"]: d for d in client.get("/api/docqa/documents").json()}
    assert listed[doc]["stale"] is True
    r = client.post(f"/api/docqa/documents/{doc}/reprocess")
    assert r.status_code == 202 and r.json()["status"] == "processing"
    after = {d["id"]: d for d in client.get("/api/docqa/documents").json()}[doc]
    assert after["status"] == "ready" and after["stale"] is False and after["chunkCount"] == 2
    assert client.post("/api/docqa/ask", json={"question": "revenue", "documentIds": [doc]}).json()["chunks"]


def test_reprocess_retries_a_failed_document_and_keeps_chunk_settings(client):
    doc = upload(client).json()["id"]
    from sqlalchemy import text

    from docqa import db
    with db.engine().begin() as conn:
        conn.execute(text("UPDATE documents SET status = 'failed', error = 'boom', chunk_count = 0 WHERE id = :i"), {"i": doc})
        conn.execute(text("DELETE FROM chunks WHERE document_id = :i"), {"i": doc})
    assert client.post(f"/api/docqa/documents/{doc}/reprocess").status_code == 202
    after = {d["id"]: d for d in client.get("/api/docqa/documents").json()}[doc]
    assert after["status"] == "ready" and after["error"] is None and (after["chunkWords"], after["chunkOverlap"]) == (300, 50)


def test_reprocess_refuses_other_users_missing_files_and_busy_documents(client, monkeypatch):
    assert client.post("/api/docqa/documents/9999/reprocess").status_code == 404
    doc = upload(client).json()["id"]
    from sqlalchemy import text

    from docqa import db
    with db.engine().begin() as conn:
        conn.execute(text("UPDATE documents SET status = 'processing' WHERE id = :i"), {"i": doc})
    busy = client.post(f"/api/docqa/documents/{doc}/reprocess")
    assert busy.status_code == 409 and busy.json()["detail"]["error"] == "already_processing"
    with db.engine().begin() as conn:
        conn.execute(text("UPDATE documents SET status = 'failed' WHERE id = :i"), {"i": doc})
    from docqa import api
    monkeypatch.setattr(api, "get_storage", lambda: type("S", (), {"get": staticmethod(lambda key: (_ for _ in ()).throw(FileNotFoundError()))})())
    gone = client.post(f"/api/docqa/documents/{doc}/reprocess")
    assert gone.status_code == 409 and gone.json()["detail"]["error"] == "file_missing"


def test_a_failure_while_saving_marks_the_document_failed_not_stuck(client, monkeypatch):
    from docqa import providers
    monkeypatch.setattr(providers, "embed", lambda texts, query: [[0.0] * 3 for _ in texts])   # wrong size: fails at commit
    doc = upload(client).json()["id"]
    got = {d["id"]: d for d in client.get("/api/docqa/documents").json()}[doc]
    assert got["status"] == "failed" and "saving" in got["error"]
    assert client.post(f"/api/docqa/documents/{doc}/reprocess").status_code in (202, 409)   # not rejected as busy


def test_uploading_a_file_that_is_still_being_processed_is_refused(client):
    data = _pdf(["quarterly revenue grew twelve percent"])
    doc = upload(client, data=data).json()["id"]
    from sqlalchemy import text

    from docqa import db
    with db.engine().begin() as conn:
        conn.execute(text("UPDATE documents SET status = 'processing' WHERE id = :i"), {"i": doc})
    again = upload(client, data=data)
    assert again.status_code == 409 and again.json()["detail"]["error"] == "already_processing"
    assert len(client.get("/api/docqa/documents").json()) == 1       # the running job's row is untouched


def test_a_model_that_cannot_load_is_a_clear_error(monkeypatch):
    import fastembed

    from docqa import providers

    def boom(*a, **k):
        raise RuntimeError("no network")
    monkeypatch.setattr(providers, "_local", None)
    monkeypatch.setattr(fastembed, "TextEmbedding", boom)
    with pytest.raises(providers.ProviderError, match="could not be loaded"):
        providers._embed_local(["hello"])
