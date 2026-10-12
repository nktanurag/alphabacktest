import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from alphabacktest import auth, orm  # noqa: F401
from alphabacktest.api import app
from alphabacktest.db import Base, get_db
from alphabacktest.orm import User

DEF = {"name": "t", "asset": "TSLA", "startDate": "2022-01-01", "endDate": "2024-12-31",
       "entryConditions": [{"id": "1", "left": {"name": "RSI", "period": 14}, "operator": "less_than",
                            "right": {"kind": "value", "value": 30}}],
       "exitDays": 10, "initialCapital": 1000, "positionSizePct": 100, "commissionPct": 0, "slippagePct": 0}

CLAIMS = {
    "good-alice": {"sub": "g-1", "email": "alice@x.com", "email_verified": True, "name": "Alice"},
    "good-bob": {"sub": "g-2", "email": "bob@x.com", "email_verified": True, "name": "Bob"},
    "unverified": {"sub": "g-3", "email": "eve@x.com", "email_verified": False},
}


def fake_verify(credential: str) -> dict:
    if credential not in CLAIMS:
        raise ValueError("bad token")
    return CLAIMS[credential]


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = override
    yield Session
    app.dependency_overrides.clear()


@pytest.fixture()
def on(session_factory, monkeypatch):
    """Auth switched on, with Google's verification replaced by a fake."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setattr(auth, "verify_google_credential", fake_verify)
    return session_factory


def new_client():
    return TestClient(app)  # each client has its own cookie jar


def login(client, credential):
    return client.post("/api/auth/google", json={"credential": credential})


def test_config_reports_client_id(on):
    assert new_client().get("/api/auth/config").json() == {"googleClientId": "test-client.apps.googleusercontent.com"}


def test_config_is_null_when_auth_is_off(session_factory):
    assert new_client().get("/api/auth/config").json() == {"googleClientId": None}


def test_protected_routes_need_login(on):
    c = new_client()
    assert c.get("/api/strategies").status_code == 401
    assert c.get("/api/strategies").json()["detail"]["error"] == "not_authenticated"
    assert c.post("/api/strategies", json={"name": "A", "definition": DEF}).status_code == 401
    assert c.get("/api/auth/me").status_code == 401


def test_login_sets_http_only_cookie_and_unlocks_routes(on):
    c = new_client()
    r = login(c, "good-alice")
    assert r.status_code == 200 and r.json()["email"] == "alice@x.com" and r.json()["name"] == "Alice"
    assert "httponly" in r.headers["set-cookie"].lower()
    assert c.get("/api/auth/me").json()["email"] == "alice@x.com"
    assert c.post("/api/strategies", json={"name": "A", "definition": DEF}).status_code == 201
    assert [s["name"] for s in c.get("/api/strategies").json()] == ["A"]


def test_users_cannot_see_each_others_strategies(on):
    alice, bob = new_client(), new_client()
    login(alice, "good-alice")
    login(bob, "good-bob")
    sid = alice.post("/api/strategies", json={"name": "Secret", "definition": DEF}).json()["id"]
    assert bob.get("/api/strategies").json() == []
    assert bob.get(f"/api/strategies/{sid}").status_code == 404
    assert bob.delete(f"/api/strategies/{sid}").status_code == 404
    assert alice.get(f"/api/strategies/{sid}").status_code == 200


def test_login_twice_reuses_the_user(on):
    login(new_client(), "good-alice")
    login(new_client(), "good-alice")
    with on() as s:
        assert s.scalar(select(func.count()).select_from(User).where(User.email == "alice@x.com")) == 1


def test_google_login_links_an_existing_row_with_the_same_email(on):
    with on() as s:
        s.add(User(email="alice@x.com"))
        s.commit()
    login(new_client(), "good-alice")
    with on() as s:
        users = s.scalars(select(User)).all()
        assert len(users) == 1 and users[0].auth_provider == "google" and users[0].auth_provider_id == "g-1"


def test_bad_token_and_unverified_email_are_rejected(on):
    c = new_client()
    assert login(c, "garbage").status_code == 401
    assert login(c, "unverified").status_code == 401
    assert c.get("/api/strategies").status_code == 401


def test_tampered_cookie_is_rejected(on):
    c = new_client()
    login(c, "good-alice")
    c.cookies.set("session", "tampered")
    assert c.get("/api/strategies").status_code == 401


def test_logout_clears_session(on):
    c = new_client()
    login(c, "good-alice")
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/strategies").status_code == 401


def test_google_login_rejected_when_auth_is_off(session_factory):
    r = login(new_client(), "good-alice")
    assert r.status_code == 400 and r.json()["detail"]["error"] == "auth_disabled"


def test_startup_requires_a_session_secret(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "x")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        auth.check_config()
