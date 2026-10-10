import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from alphabacktest.api import app
from alphabacktest.db import Base, get_db
from alphabacktest import orm  # noqa: F401

DEF = {"name": "t", "asset": "TSLA", "startDate": "2022-01-01", "endDate": "2024-12-31",
       "entryConditions": [{"id": "1", "left": {"name": "RSI", "period": 14}, "operator": "less_than",
                            "right": {"kind": "value", "value": 30}}],
       "exitDays": 10, "initialCapital": 1000, "positionSizePct": 100, "commissionPct": 0, "slippagePct": 0}


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_crud_roundtrip(client):
    r = client.post("/api/strategies", json={"name": "A", "description": "d", "definition": DEF})
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["definition"]["entryConditions"][0]["left"]["name"] == "RSI"

    assert [s["name"] for s in client.get("/api/strategies").json()] == ["A"]
    assert client.get(f"/api/strategies/{sid}").json()["definition"]["exitDays"] == 10

    r = client.put(f"/api/strategies/{sid}", json={"name": "B", "definition": {**DEF, "exitDays": 5}})
    assert r.status_code == 200 and r.json()["name"] == "B" and r.json()["definition"]["exitDays"] == 5

    assert client.delete(f"/api/strategies/{sid}").status_code == 204
    assert client.get(f"/api/strategies/{sid}").status_code == 404


def test_duplicate_name_conflict(client):
    client.post("/api/strategies", json={"name": "A", "definition": DEF})
    r = client.post("/api/strategies", json={"name": "A", "definition": DEF})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "name_taken"


def test_invalid_definition_rejected(client):
    bad = {**DEF, "exitDays": "x"}
    assert client.post("/api/strategies", json={"name": "A", "definition": bad}).status_code == 422


def test_strategies_are_private_per_user(client):
    from alphabacktest.orm import User
    from alphabacktest.strategies import current_user

    sessions = app.dependency_overrides[get_db]
    with next(sessions()) as s:
        alice, bob = User(email="alice@x.com"), User(email="bob@x.com")
        s.add_all([alice, bob])
        s.commit()
        ids = {"alice": alice.id, "bob": bob.id}

    def as_user(name):
        def dep():
            with next(sessions()) as s:
                return s.get(User, ids[name])
        app.dependency_overrides[current_user] = dep

    as_user("alice")
    sid = client.post("/api/strategies", json={"name": "Secret", "definition": DEF}).json()["id"]

    as_user("bob")
    assert client.get("/api/strategies").json() == []
    assert client.get(f"/api/strategies/{sid}").status_code == 404
    assert client.put(f"/api/strategies/{sid}", json={"name": "X", "definition": DEF}).status_code == 404
    assert client.delete(f"/api/strategies/{sid}").status_code == 404
    # Bob can reuse the same name: uniqueness is per user.
    assert client.post("/api/strategies", json={"name": "Secret", "definition": DEF}).status_code == 201

    as_user("alice")
    assert [x["name"] for x in client.get("/api/strategies").json()] == ["Secret"]
    assert client.get(f"/api/strategies/{sid}").status_code == 200
