from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal, init_db
from app.main import app
from app.providers.mock import market_state
from app.repositories.snapshots import VisitRepository
from app.services.market import market_service


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def session(client):
    response = client.post("/api/auth/demo")
    assert response.status_code == 200
    return response.json()


@pytest.fixture(scope="module")
def watchlist_id(client, session):
    lists = client.get("/api/watchlists").json()
    assert lists, "a new account should be seeded with a starter watchlist"
    return lists[0]["id"]


def test_health_reports_dependencies(client):
    body = client.get("/api/health").json()
    assert body["status"] in {"ok", "degraded"}
    assert body["database"] is True
    assert len(body["providers"]) == 2


def test_unauthenticated_requests_are_rejected():
    with TestClient(app) as anon:
        assert anon.get("/api/watchlists").status_code == 401


def test_demo_login_is_idempotent(client):
    first = client.post("/api/auth/demo").json()
    second = client.post("/api/auth/demo").json()
    assert first["id"] == second["id"]
    assert len(client.get("/api/watchlists").json()) == 2


def test_registration_validates_input(client):
    assert client.post("/api/auth/register", json={"email": "nope", "password": "x" * 9}).status_code == 422
    assert client.post("/api/auth/register", json={"email": "a@b.com", "password": "short"}).status_code == 422


def test_watchlist_crud(client, session):
    created = client.post("/api/watchlists", json={"name": "Energy", "symbols": ["XOM", "CVX"]})
    assert created.status_code == 201
    wl = created.json()
    assert wl["itemCount"] == 2

    assert client.post("/api/watchlists", json={"name": "Energy"}).status_code == 409

    renamed = client.patch(f"/api/watchlists/{wl['id']}", json={"name": "Energy majors"})
    assert renamed.json()["name"] == "Energy majors"

    added = client.post(f"/api/watchlists/{wl['id']}/stocks", json={"symbol": "oxy"})
    assert added.status_code == 201
    assert "OXY" in [i["symbol"] for i in added.json()["items"]]

    assert client.post(f"/api/watchlists/{wl['id']}/stocks", json={"symbol": "OXY"}).status_code == 409
    assert client.post(f"/api/watchlists/{wl['id']}/stocks", json={"symbol": "FAKE"}).status_code == 404
    assert client.post(f"/api/watchlists/{wl['id']}/stocks", json={"symbol": "../etc"}).status_code == 422

    reordered = client.post(
        f"/api/watchlists/{wl['id']}/reorder", json={"symbols": ["OXY", "CVX", "XOM"]}
    ).json()
    assert [i["symbol"] for i in reordered["items"]] == ["OXY", "CVX", "XOM"]

    assert client.delete(f"/api/watchlists/{wl['id']}/stocks/OXY").status_code == 200
    assert client.delete(f"/api/watchlists/{wl['id']}/stocks/OXY").status_code == 404
    assert client.delete(f"/api/watchlists/{wl['id']}").status_code == 204


def test_other_users_watchlists_are_invisible(client, watchlist_id):
    with TestClient(app) as other:
        other.post(
            "/api/auth/register",
            json={"email": "someone@else.com", "password": "correct-horse"},
        )
        assert other.get(f"/api/watchlists/{watchlist_id}/overview").status_code == 404


def test_overview_shape(client, watchlist_id):
    body = client.get(f"/api/watchlists/{watchlist_id}/overview").json()
    assert body["summary"]["tracked"] == len(body["items"])
    assert body["items"] == sorted(body["items"], key=lambda i: -i["attentionScore"])

    item = body["items"][0]
    assert set(item["changes"]) == {"sinceVisitPct", "todayPct", "weekPct"}
    assert item["freshness"]["state"] in {"fresh", "delayed", "stale", "unavailable"}
    assert item["confidence"]["level"] in {"high", "medium", "low"}
    # the score is the sum of its signals, and every signal carries its reason
    assert item["attentionScore"] == round(min(100, sum(s["contribution"] for s in item["signals"])))
    assert all(s["detail"] for s in item["signals"])
    assert body["indices"], "benchmarks must be published alongside the items"


def test_polling_does_not_move_the_baseline(client, watchlist_id):
    """The bug that makes most watchlists useless: refresh resets 'since last check'."""
    first = client.get(f"/api/watchlists/{watchlist_id}/overview").json()
    baseline = {i["symbol"]: i["baseline"]["price"] for i in first["items"]}

    for _ in range(3):
        again = client.get(f"/api/watchlists/{watchlist_id}/overview").json()
        assert {i["symbol"]: i["baseline"]["price"] for i in again["items"]} == baseline


def test_a_new_visit_rebaselines_to_what_the_user_last_saw(client, watchlist_id, session):
    seen = {
        i["symbol"]: i["price"]
        for i in client.get(f"/api/watchlists/{watchlist_id}/overview").json()["items"]
    }

    # Simulate walking away: age the visit past the idle timeout.
    with SessionLocal() as db:
        visit, _prev, _new = VisitRepository(db).current_or_new(session["id"], watchlist_id, 900)
        visit.last_seen_at = datetime.now(UTC) - timedelta(hours=4)
        db.commit()

    market_service.invalidate()
    body = client.get(f"/api/watchlists/{watchlist_id}/overview").json()
    assert body["visit"]["isNewVisit"] is True
    assert body["visit"]["awaySeconds"] > 3600
    assert body["visit"]["baselineSource"] == "last_visit"
    for item in body["items"]:
        assert item["baseline"]["price"] == pytest.approx(seen[item["symbol"]], rel=1e-9)


def test_inbox_review_flow(client, watchlist_id, session):
    from datetime import UTC, datetime, timedelta
    from sqlalchemy import text
    # 1. Quiet market — open a visit and record what the user "saw".
    client.post(f"/api/watchlists/{watchlist_id}/baseline/reset")
    market_state.select_scenario("NORMAL_MARKET")
    market_service.invalidate()
    client.get(f"/api/watchlists/{watchlist_id}/overview")

    # 2. Simulate 2-hour absence.
    past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    with SessionLocal() as db:
        db.execute(text("UPDATE visits SET last_seen_at=:t, started_at=:t WHERE watchlist_id=:w"), {"t": past, "w": watchlist_id})
        db.execute(text("UPDATE user_snapshots SET observed_at=:t WHERE watchlist_id=:w"), {"t": past, "w": watchlist_id})
        db.commit()

    # 3. Return to a breakout.
    market_state.select_scenario("NVDA_BREAKOUT")
    market_service.invalidate()
    client.get(f"/api/watchlists/{watchlist_id}/overview")

    changes = client.get(f"/api/watchlists/{watchlist_id}/changes").json()
    assert changes, "a scripted breakout should produce at least one change event"

    event = changes[0]
    reviewed = client.post(f"/api/events/{event['id']}/review", json={"status": "reviewed"}).json()
    assert reviewed["status"] == "reviewed"
    assert reviewed["reviewedAt"] is not None

    still_reviewed = client.get(f"/api/watchlists/{watchlist_id}/changes").json()
    assert next(c for c in still_reviewed if c["id"] == event["id"])["status"] == "reviewed"

    new_only = client.get(f"/api/watchlists/{watchlist_id}/changes?status=new").json()
    assert event["id"] not in [c["id"] for c in new_only]

    assert client.post("/api/events/999999/review", json={"status": "reviewed"}).status_code == 404


def test_repeated_polling_does_not_duplicate_change_events(client, watchlist_id):
    before = client.get(f"/api/watchlists/{watchlist_id}/changes").json()
    for _ in range(4):
        client.get(f"/api/watchlists/{watchlist_id}/overview")
    after = client.get(f"/api/watchlists/{watchlist_id}/changes").json()
    assert len(after) == len(before)


def test_review_all_and_baseline_reset(client, watchlist_id):
    client.get(f"/api/watchlists/{watchlist_id}/overview")
    client.post(f"/api/watchlists/{watchlist_id}/changes/review-all")
    assert client.get(f"/api/watchlists/{watchlist_id}/inbox-count").json()["new"] == 0

    assert client.post(f"/api/watchlists/{watchlist_id}/baseline/reset").status_code == 204
    body = client.get(f"/api/watchlists/{watchlist_id}/overview").json()
    assert body["visit"]["isNewVisit"] is True


def test_search_and_stock_detail(client):
    results = client.get("/api/stocks/search?q=nvid").json()
    assert results[0]["symbol"] == "NVDA"
    assert client.get("/api/stocks/search?q=zzzz").json() == []

    detail = client.get("/api/stocks/NVDA").json()
    assert detail["sectorLabel"] == "Semiconductors"
    assert len(detail["history"]) == 60
    assert detail["freshness"]["source"]

    assert client.get("/api/stocks/FAKE").status_code == 404
    assert len(client.get("/api/stocks/NVDA/history?days=30").json()) == 30


def test_demo_controls_switch_the_tape(client, watchlist_id):
    state = client.post("/api/demo/state", json={"scenario": "TSLA_DROP"}).json()
    assert state["scenario"] == "TSLA_DROP"
    assert len(state["scenarios"]) == 6

    body = client.get(f"/api/watchlists/{watchlist_id}/overview").json()
    tsla = next(i for i in body["items"] if i["symbol"] == "TSLA")
    assert tsla["changes"]["todayPct"] < 0

    assert client.post("/api/demo/state", json={"scenario": "NOPE"}).status_code == 400


def test_stale_feed_lowers_confidence_end_to_end(client, watchlist_id):
    client.post("/api/demo/state", json={"scenario": "STALE_PROVIDER"})
    body = client.get(f"/api/watchlists/{watchlist_id}/overview").json()
    assert body["dataQuality"]["freshness"] in {"delayed", "stale", "unavailable"}
    assert any(i["confidence"]["level"] != "high" for i in body["items"])


def test_provider_conflict_surfaces_in_data_quality(client, watchlist_id):
    client.post("/api/demo/state", json={"scenario": "CONFLICTING_PROVIDER"})
    body = client.get(f"/api/watchlists/{watchlist_id}/overview").json()
    assert body["dataQuality"]["discrepancies"], "a disagreement must be surfaced, not swallowed"
    logs = client.get("/api/data-quality").json()
    assert any(row["kind"] == "discrepancy" for row in logs)


def test_provider_outage_degrades_without_breaking(client, watchlist_id):
    client.post("/api/demo/state", json={"primaryOutage": True, "secondaryOutage": True})
    body = client.get(f"/api/watchlists/{watchlist_id}/overview")
    assert body.status_code == 200, "the page must never fail because a feed did"
    payload = body.json()
    assert payload["dataQuality"]["degraded"] is True
    assert payload["items"], "the last verified snapshot should still be served"
    client.post("/api/demo/state", json={"primaryOutage": False, "secondaryOutage": False})


def test_attention_profile_round_trip(client):
    client.put("/api/settings/attention", json={"weights": {"price_move": 45, "bogus": 9}})
    profile = client.get("/api/settings/attention").json()
    assert profile["weights"]["price_move"] == 45.0
    assert "bogus" not in profile["weights"]
    client.put("/api/settings/attention", json={"weights": profile["defaults"]})


def test_logout_clears_the_session(client):
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
