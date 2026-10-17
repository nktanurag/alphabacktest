from docqa import providers


class _Res:
    ok = True
    status_code = 200
    text = ""

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def test_list_keeps_only_text_generators_and_follows_pages(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(providers, "_models_cache", None)
    pages = [
        {"models": [
            {"name": "models/gemini-3.8-flash", "displayName": "Gemini 3.8 Flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-3.8-flash-tts", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-2.5-flash-image", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]}],
         "nextPageToken": "p2"},
        {"models": [{"name": "models/gemini-flash-latest", "supportedGenerationMethods": ["generateContent", "countTokens"]},
                    {"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["embedContent"]},
                    {"name": "models/gemma-3-27b", "supportedGenerationMethods": ["generateContent"]}]},
    ]
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params)
        return _Res(pages[len(calls) - 1])
    monkeypatch.setattr(providers.requests, "get", fake_get)
    got = providers.list_generation_models()
    assert [m["id"] for m in got] == ["gemini-3.8-flash", "gemini-flash-latest"]
    assert got[0]["name"] == "Gemini 3.8 Flash" and calls[1]["pageToken"] == "p2"
    providers.list_generation_models()
    assert len(calls) == 2   # second call is served from the cache
    monkeypatch.setattr(providers, "_models_cache", None)
