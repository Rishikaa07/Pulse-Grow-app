"""The product's core journey, exercised end to end.

This is the demo script as a test: sit on a quiet market, walk away, come back
to a scripted breakout, and assert that the product says the right things at
each step. It is the test most likely to catch a regression that unit tests
would miss, because "what changed since you last looked" is an emergent
property of the visit model, the tape and the engine together.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal, init_db
from app.main import app
from app.services.market import market_service


@pytest.fixture(scope="module")
def client():
    """A user of its own, so this journey is not disturbed by other suites."""
    init_db()
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "journey@example.com", "password": "walk-away-01"})
        yield c


@pytest.fixture(scope="module")
def watchlist_id(client) -> int:
    lists = client.get("/api/watchlists").json()
    assert lists, "seed should have created starter watchlists on registration"
    return lists[0]["id"]


def walk_away(watchlist_id: int, hours: float) -> None:
    """Age the visit *and* the observations it recorded.

    Both must move together: the visit decides whether you are back, and the
    observation timestamp decides how long a window the move is judged against.
    """
    past = datetime.now(UTC) - timedelta(hours=hours)
    with SessionLocal() as db:
        db.execute(
            text("UPDATE visits SET last_seen_at = :t, started_at = :t WHERE watchlist_id = :w"),
            {"t": past.isoformat(), "w": watchlist_id},
        )
        db.execute(
            text("UPDATE user_snapshots SET observed_at = :t WHERE watchlist_id = :w"),
            {"t": past.isoformat(), "w": watchlist_id},
        )
        db.commit()
    market_service.invalidate()


def overview(client: TestClient, watchlist_id: int) -> dict:
    response = client.get(f"/api/watchlists/{watchlist_id}/overview")
    assert response.status_code == 200
    return response.json()


def test_the_full_journey(client, watchlist_id):
    # Ensure a clean scenario regardless of what other test suites left behind.
    client.post("/api/demo/state", json={"scenario": "NORMAL_MARKET",
                                         "primaryOutage": False,
                                         "secondaryOutage": False})
    # --- 1. a quiet market says so, loudly -----------------------------------
    market_service.invalidate()
    quiet = overview(client, watchlist_id)

    assert quiet["visit"]["baselineSource"] == "session_open"
    assert quiet["summary"]["meaningfulChanges"] == 0
    assert all(item["severity"] in {"none", "low"} for item in quiet["items"]), (
        "a market with no scripted shock must not manufacture urgency"
    )
    assert all(
        item["headline"] in {"Moving with the market", "Worth a look"}
        or "Notable" in item["headline"]
        for item in quiet["items"]
    )

    seen = {item["symbol"]: item["price"] for item in quiet["items"]}

    # --- 2. walk away for three hours; the market breaks out -----------------
    walk_away(watchlist_id, 3.3)
    client.post("/api/demo/state", json={"scenario": "NVDA_BREAKOUT"})
    back = overview(client, watchlist_id)

    visit = back["visit"]
    assert visit["isNewVisit"] is True
    assert visit["baselineSource"] == "last_visit"
    assert 11_000 < visit["awaySeconds"] < 12_500

    # every baseline is exactly the price the user last saw
    for item in back["items"]:
        assert item["baseline"]["price"] == pytest.approx(seen[item["symbol"]], rel=1e-9)

    # --- 3. the breakout is the top of the feed, and it is explained ---------
    high_items = [i for i in back["items"] if i["severity"] == "high"]
    assert high_items, "NVDA_BREAKOUT must surface at least one high-severity item"
    top = high_items[0]
    semi_high = [i for i in high_items if i["symbol"] in {"NVDA", "AMD", "TSM", "AVGO"}]
    assert semi_high, f"breakout should lift at least one semi into high; got {[i['symbol'] for i in high_items]}"
    top = semi_high[0]
    assert top["attentionScore"] >= 60
    assert top["changes"]["sinceVisitPct"] > 1.0
    assert top["volumeRatio"] is not None and top["volumeRatio"] > 1.2  # floor in the scoring function
    assert top["benchmarks"]["relativeEdgePct"] is not None

    # the sigma multiple is scaled to a three-hour window, not a whole session
    assert 1.0 < (top["sigmaMultiple"] or 0) < 8.0

    # the explanation is assembled from the signals that actually scored
    scoring = [s for s in top["signals"] if s["contribution"] >= 1]
    assert scoring, "a high-severity item must have scoring signals"
    assert scoring[0]["detail"].rstrip(".") in top["explanation"]

    # --- 4. the noise floor holds --------------------------------------------
    flagged = [i for i in back["items"] if i["severity"] == "high"]
    assert 1 <= len(flagged) <= 4, (
        f"a single-name breakout should flag a handful of names, not {len(flagged)}"
    )

    # --- 5. reviewing clears the inbox and it stays cleared -------------------
    assert back["summary"]["newInInbox"] > 0
    client.post(f"/api/watchlists/{watchlist_id}/changes/review-all")
    after = overview(client, watchlist_id)
    assert after["summary"]["newInInbox"] == 0
    assert all(item["status"] != "new" for item in after["items"] if item["changeEventId"])


def test_headline_never_contradicts_its_own_measurement(client, watchlist_id):
    """A 0.4% drift must not be headlined as an unusually large move."""
    client.post("/api/demo/state", json={"scenario": "NORMAL_MARKET",
                                         "primaryOutage": False, "secondaryOutage": False})
    market_service.invalidate()
    body = overview(client, watchlist_id)

    for item in body["items"]:
        sigma = item["sigmaMultiple"]
        if "Unusually large" in item["headline"]:
            assert sigma is not None and sigma >= 2.0, (
                f"{item['symbol']} called unusual at {sigma} sigma"
            )


def test_relative_signals_do_not_fire_on_a_flat_stock(client, watchlist_id):
    """Sector drift alone must not accumulate points for a stock that didn't move."""
    client.post("/api/demo/state", json={"scenario": "NORMAL_MARKET",
                                         "primaryOutage": False, "secondaryOutage": False})
    market_service.invalidate()
    body = overview(client, watchlist_id)

    for item in body["items"]:
        sigma = item["sigmaMultiple"] or 0
        if sigma >= 0.4:
            continue
        relative = [
            s
            for s in item["signals"]
            if s["type"] in {"SECTOR_OUTPERFORMANCE", "MARKET_OUTPERFORMANCE"}
        ]
        assert all(s["contribution"] < 1 for s in relative), (
            f"{item['symbol']} scored on benchmarks without moving"
        )
