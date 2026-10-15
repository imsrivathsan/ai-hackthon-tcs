from fastapi.testclient import TestClient
import pytest

from app.db import Base, SessionLocal, engine
from app.main import app
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


def test_health_check(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "Meridian"
    assert data["version"] == "1.0.0"


def test_list_competitors(client):
    response = client.get("/api/v1/competitors")
    assert response.status_code == 200
    competitors = response.json()
    assert len(competitors) == 6

    ids = [c["id"] for c in competitors]
    assert "marsh-mclennan" in ids
    assert "aon" in ids
    assert "wtw" in ids
    assert "arthur-j-gallagher" in ids
    assert "brown-and-brown" in ids
    assert "hub-international" in ids

    # Check fields of one competitor
    mmc = next(c for c in competitors if c["id"] == "marsh-mclennan")
    assert mmc["name"] == "Marsh McLennan"
    assert mmc["ticker"] == "MMC"
    assert mmc["headquarters"] == "New York, NY"
    assert mmc["market_cap_tier"] == "Mega-Cap"


def test_get_competitor_by_id(client):
    response = client.get("/api/v1/competitors/marsh-mclennan")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "marsh-mclennan"
    assert data["name"] == "Marsh McLennan"


def test_get_competitor_not_found(client):
    response = client.get("/api/v1/competitors/non-existent-broker")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "detail" in data
    assert "not found" in data["error"].lower()


def test_get_battlecard(client):
    response = client.get("/api/v1/competitors/marsh-mclennan/battlecard")
    assert response.status_code == 200
    card = response.json()

    # Exact Battlecard schema verification
    assert card["competitor"] == "Marsh McLennan"
    assert card["severity"] in ["High", "Medium", "Low"]
    assert isinstance(card["threat_score"], int)
    assert 0 <= card["threat_score"] <= 100
    assert isinstance(card["headline"], str) and len(card["headline"]) > 0
    assert isinstance(card["subtext"], str) and len(card["subtext"]) > 0

    # Exactly 3 wins
    assert len(card["wins"]) == 3
    for win in card["wins"]:
        assert "title" in win
        assert "text" in win
        assert win["source_url"].startswith("http")

    # Exactly 3 moves
    assert len(card["moves"]) == 3
    for move in card["moves"]:
        assert move["tag"] in ["M&A", "Leadership", "Product", "Pricing"]
        assert "summary" in move
        assert "date" in move
        assert move["source_url"].startswith("http")

    # Metrics pure computation shape
    metrics = card["metrics"]
    assert isinstance(metrics["ma_deals_12m"], int)
    assert isinstance(metrics["activity_trend"], list)
    assert len(metrics["activity_trend"]) == 6
    assert all(isinstance(x, int) for x in metrics["activity_trend"])
    assert isinstance(metrics["evidence_confidence"], int)
    assert metrics["evidence_confidence"] >= 1

    assert "updated_at" in card


def test_all_six_battlecards_available(client):
    comp_ids = [
        "marsh-mclennan",
        "aon",
        "wtw",
        "arthur-j-gallagher",
        "brown-and-brown",
        "hub-international",
    ]
    for cid in comp_ids:
        response = client.get(f"/api/v1/competitors/{cid}/battlecard")
        assert response.status_code == 200, f"Failed for competitor {cid}"
        card = response.json()
        assert len(card["wins"]) == 3
        assert len(card["moves"]) == 3
        assert len(card["metrics"]["activity_trend"]) == 6


def test_battlecard_not_found(client):
    response = client.get("/api/v1/competitors/unknown-id/battlecard")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "detail" in data


def test_get_overview(client):
    response = client.get("/api/v1/overview")
    assert response.status_code == 200
    data = response.json()

    assert "competitors" in data
    assert "total_competitors" in data
    assert data["total_competitors"] == 6
    assert len(data["competitors"]) == 6

    # Verify ranked order (threat_score descending)
    scores = [c["threat_score"] for c in data["competitors"]]
    assert scores == sorted(scores, reverse=True)

    # Verify fields on top competitor
    top = data["competitors"][0]
    assert "id" in top
    assert "threat_score" in top
    assert "severity" in top
    assert "ma_deals_12m" in top
    assert "activity_trend" in top
    assert "evidence_confidence" in top

    # Verify quarterly M&A trends
    assert "quarterly_ma" in data
    assert len(data["quarterly_ma"]) >= 1
    for q in data["quarterly_ma"]:
        assert "quarter" in q
        assert "deals" in q


def test_get_feed_pagination_and_filters(client):
    # 1. Basic feed list
    response = client.get("/api/v1/feed?page=1&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) <= 5
    assert data["page"] == 1
    assert data["limit"] == 5
    assert data["total"] >= 20

    # 2. Tag filter
    response_ma = client.get("/api/v1/feed?tag=M%26A")
    assert response_ma.status_code == 200
    data_ma = response_ma.json()
    for item in data_ma["items"]:
        assert item["tag"] == "M&A"

    # 3. Competitor filter
    response_comp = client.get("/api/v1/feed?competitor=marsh-mclennan")
    assert response_comp.status_code == 200
    data_comp = response_comp.json()
    for item in data_comp["items"]:
        assert item["competitor_id"] == "marsh-mclennan"


def test_generate_meeting_brief(client):
    response = client.post("/api/v1/competitors/marsh-mclennan/brief")
    assert response.status_code == 200
    data = response.json()

    assert data["competitor_id"] == "marsh-mclennan"
    assert data["competitor_name"] == "Marsh McLennan"
    assert "talk_track" in data
    assert len(data["talk_track"]) == 5
    assert "brief_text" in data
    assert "model_used" in data
    assert "generated_at" in data


def test_post_ask_grounded(client):
    payload = {
        "question": "What M&A acquisitions did Marsh McLennan complete recently?",
        "competitor_id": "marsh-mclennan",
        "tag": "M&A",
    }
    response = client.post("/api/v1/ask", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["question"] == payload["question"]
    assert "answer" in data
    assert len(data["answer"]) > 0
    assert "citations" in data
    assert isinstance(data["citations"], list)
    assert "model_used" in data
    assert "retrieved_count" in data
    assert data["retrieved_count"] <= 12
    # Verify citations if present
    if data["citations"]:
        c = data["citations"][0]
        assert "id" in c
        assert "source_url" in c
        assert c["competitor_id"] == "marsh-mclennan"


def test_post_ask_no_evidence(client):
    payload = {
        "question": "What is the quantum satellite launched by NASA to Mars?",
    }
    response = client.post("/api/v1/ask", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "answer" in data
    assert "No evidence found" in data["answer"]
    assert len(data["citations"]) == 0


def test_post_ask_greeting(client):
    for greeting in ["hi", "Hello!", "hey"]:
        response = client.post("/api/v1/ask", json={"question": greeting})
        assert response.status_code == 200
        data = response.json()
        assert "Hello! I am Meridian" in data["answer"]
        assert len(data["citations"]) == 0


def test_auth_profiles(client):
    res = client.get("/api/v1/auth/profiles")
    assert res.status_code == 200
    profiles = res.json()
    assert len(profiles) >= 3
    assert any(p["name"] == "Sarah Jenkins" for p in profiles)


def test_auth_login_success(client):
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "analyst@meridian.intel", "password": "password123"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert data["user"]["email"] == "analyst@meridian.intel"
    assert data["user"]["name"] == "Sarah Jenkins"




