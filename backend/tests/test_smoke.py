import time
from fastapi.testclient import TestClient
import pytest

from app.db import Base, SessionLocal, engine
from app.main import app
from app.routers.admin import _RATE_LIMITS
from app.services.seed import load_seed_data


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        load_seed_data(session, force=True)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_smoke_health(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["app"] == "Meridian"


def test_smoke_competitors(client):
    res = client.get("/api/v1/competitors")
    assert res.status_code == 200
    competitors = res.json()
    assert len(competitors) == 6
    for c in competitors:
        assert "id" in c
        assert "name" in c
        assert "headquarters" in c


def test_smoke_battlecard(client):
    res = client.get("/api/v1/competitors/aon/battlecard")
    assert res.status_code == 200
    card = res.json()
    assert card["competitor"] == "Aon"
    assert len(card["wins"]) == 3
    assert len(card["moves"]) == 3
    assert "metrics" in card
    assert 0 <= card["threat_score"] <= 100


def test_smoke_overview_with_market_insight(client):
    res = client.get("/api/v1/overview")
    assert res.status_code == 200
    data = res.json()
    assert "competitors" in data
    assert len(data["competitors"]) == 6
    assert "quarterly_ma" in data
    # Phase 5 Market Insight check
    assert "market_insight" in data
    insight = data["market_insight"]
    assert "insight" in insight
    assert "model_used" in insight
    assert len(insight["insight"]) > 0


def test_smoke_feed(client):
    res = client.get("/api/v1/feed?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert len(data["items"]) <= 10
    assert data["total"] > 0


def test_smoke_brief(client):
    res = client.post("/api/v1/competitors/wtw/brief")
    assert res.status_code == 200
    data = res.json()
    assert data["competitor_id"] == "wtw"
    assert len(data["talk_track"]) == 5


def test_smoke_ask(client):
    # Greeting
    res = client.post("/api/v1/ask", json={"question": "Hello"})
    assert res.status_code == 200
    assert "Meridian" in res.json()["answer"]

    # Grounded query
    res2 = client.post("/api/v1/ask", json={"question": "What M&A deals did Aon make?", "competitor_id": "aon"})
    assert res2.status_code == 200
    assert len(res2.json()["answer"]) > 0

    # Out of scope query
    res3 = client.post("/api/v1/ask", json={"question": "What is the orbital speed of Pluto?"})
    assert res3.status_code == 200
    assert "No evidence found" in res3.json()["answer"]


def test_smoke_admin_refresh_and_rate_limit(client):
    # Clear any past history
    _RATE_LIMITS.clear()

    # 1. Successful pipeline refresh for one competitor
    res = client.post("/api/v1/admin/refresh/marsh-mclennan")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["competitor_id"] == "marsh-mclennan"
    assert data["items_upserted"] >= 0

    # 2. Test rate limiting enforcement without doing 10 slow network calls
    # Populate the rate limit tracker for client IP
    _RATE_LIMITS["testclient"] = [time.time()] * 10
    rate_res = client.post("/api/v1/admin/refresh/marsh-mclennan")
    assert rate_res.status_code == 429
    err = rate_res.json()
    assert "Rate limit exceeded" in err["detail"]

    # Cleanup rate limit history
    _RATE_LIMITS.clear()


def test_smoke_admin_refresh_not_found(client):
    _RATE_LIMITS.clear()
    res = client.post("/api/v1/admin/refresh/non-existent-broker")
    assert res.status_code == 404
    assert "not found" in res.json()["error"].lower()
