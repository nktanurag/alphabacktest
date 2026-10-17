import pytest

from docqa import providers


class _Res:
    def __init__(self, status, body=None, text=""):
        self.status_code, self._body, self.text = status, body or {}, text
        self.ok = status < 400

    def json(self):
        return self._body


def _client(monkeypatch, statuses):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)
    calls = []

    def post(url, json=None, headers=None, timeout=None):
        calls.append(url)
        status = statuses[min(len(calls) - 1, len(statuses) - 1)]
        return _Res(status, {"ok": True}, '{"error": "high demand"}')
    monkeypatch.setattr(providers.requests, "post", post)
    return calls


def test_a_busy_service_is_retried_then_succeeds(monkeypatch):
    calls = _client(monkeypatch, [503, 503, 200])
    assert providers._post("models/x:generateContent", {}) == {"ok": True}
    assert len(calls) == 3


def test_a_service_that_stays_busy_gives_a_friendly_error(monkeypatch):
    calls = _client(monkeypatch, [503])
    with pytest.raises(providers.ProviderError, match="busy"):
        providers._post("models/x:generateContent", {})
    assert len(calls) == 5


def test_other_errors_are_not_retried(monkeypatch):
    calls = _client(monkeypatch, [404])
    with pytest.raises(providers.ProviderError, match="404"):
        providers._post("models/x:generateContent", {})
    assert len(calls) == 1
