from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from ...cache import cache
from ...config import settings
from ...db.session import engine
from ...domain.attention.weights import PRESETS, AttentionWeights
from ...providers import synthetic, universe
from ...providers.mock import market_state
from ...repositories.events import ChangeEventRepository, DataQualityRepository
from ...services.market import market_service
from .. import schemas
from ..deps import CurrentUser, DbSession

router = APIRouter(tags=["market"])

APP_VERSION = "1.0.0"


@router.get("/stocks/search", response_model=list[schemas.SearchResultOut])
def search_stocks(q: str = Query(default="", max_length=64), limit: int = Query(8, ge=1, le=25)):
    return [
        schemas.SearchResultOut(
            symbol=i.symbol,
            name=i.name,
            exchange=i.exchange,
            sector=i.sector,
            sector_label=universe.sector_label(i.sector),
        )
        for i in universe.search(q, limit)
    ]


@router.get("/stocks/{symbol}", response_model=schemas.StockDetailOut)
def stock_detail(symbol: str, _user: CurrentUser):
    inst = universe.get(symbol)
    if inst is None:
        raise HTTPException(status_code=404, detail=f"{symbol.upper()} is not a symbol we track.")

    snapshot = market_service.snapshot()
    quote = snapshot.quotes.get(inst.symbol)
    if quote is None:
        raise HTTPException(
            status_code=503,
            detail="Live market data is temporarily unavailable for this symbol.",
        )

    stats = market_service.stats(inst.symbol)
    history = market_service.history(inst.symbol, days=60)
    events = [e for e in snapshot.events if e.symbol == inst.symbol]

    return schemas.StockDetailOut(
        symbol=inst.symbol,
        name=inst.name,
        exchange=inst.exchange,
        sector=inst.sector,
        sector_label=universe.sector_label(inst.sector),
        price=quote.price,
        prev_close=quote.prev_close,
        open_price=quote.open_price,
        day_high=quote.day_high,
        day_low=quote.day_low,
        volume=quote.volume,
        freshness=schemas.FreshnessOut(
            state=quote.quality.freshness,
            age_seconds=round(quote.quality.age_seconds, 1),
            source=quote.quality.selected_source,
            as_of=quote.as_of,
            notes=quote.quality.notes,
        ),
        stats={k: round(v, 6) for k, v in stats.items()},
        history=[
            schemas.HistoryPointOut(day=p.day, close=p.close, volume=p.volume) for p in history
        ],
        events=[
            schemas.EventOut(
                id=e.id, headline=e.headline, kind=e.kind, occurred_at=e.occurred_at
            )
            for e in events
        ],
    )


@router.get("/stocks/{symbol}/history", response_model=list[schemas.HistoryPointOut])
def stock_history(symbol: str, _user: CurrentUser, days: int = Query(60, ge=5, le=90)):
    if not universe.exists(symbol):
        raise HTTPException(status_code=404, detail=f"{symbol.upper()} is not a symbol we track.")
    points = market_service.history(symbol, days)
    if not points:
        raise HTTPException(status_code=503, detail="Price history is temporarily unavailable.")
    return [schemas.HistoryPointOut(day=p.day, close=p.close, volume=p.volume) for p in points]


@router.post("/events/{event_id}/review", response_model=schemas.ChangeEventOut)
def review_event(event_id: int, body: schemas.ReviewRequest, db: DbSession, user: CurrentUser):
    repo = ChangeEventRepository(db)
    event = repo.get_owned(user.id, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="That change is no longer in your inbox.")
    repo.set_status(event, body.status, user.id)
    db.commit()
    return event


@router.get("/data-quality", response_model=list[dict])
def data_quality(db: DbSession, _user: CurrentUser, limit: int = Query(20, ge=1, le=100)):
    return [
        {
            "id": row.id,
            "symbol": row.symbol,
            "kind": row.kind,
            "detail": row.detail,
            "detectedAt": row.detected_at,
        }
        for row in DataQualityRepository(db).recent(limit)
    ]


@router.get("/settings/attention", response_model=dict)
def get_attention_profile(user: CurrentUser):
    weights = AttentionWeights.from_dict(user.attention_profile)
    return {
        "weights": weights.to_dict(),
        "defaults": AttentionWeights().to_dict(),
        "presets": {name: preset.to_dict() for name, preset in PRESETS.items()},
    }


@router.put("/settings/attention", response_model=dict)
def set_attention_profile(body: schemas.AttentionProfileRequest, db: DbSession, user: CurrentUser):
    # Round-tripping through AttentionWeights drops unknown keys and coerces
    # types, so a malformed profile can never reach the engine.
    weights = AttentionWeights.from_dict(body.weights)
    user.attention_profile = weights.to_dict()
    db.commit()
    return {"weights": weights.to_dict()}


# --- demo controls -------------------------------------------------------------


@router.get("/demo/state", response_model=schemas.DemoStateOut)
def demo_state():
    return schemas.DemoStateOut(
        scenario=market_state.scenario,
        primary_outage=market_state.primary_outage,
        secondary_outage=market_state.secondary_outage,
        scenarios=[
            schemas.ScenarioOut(key=s.key, label=s.label, description=s.description)
            for s in synthetic.SCENARIOS.values()
        ],
    )


@router.post("/demo/state", response_model=schemas.DemoStateOut)
def set_demo_state(body: schemas.DemoStateRequest, _user: CurrentUser):
    if body.scenario is not None:
        key = body.scenario.upper()
        if key not in synthetic.SCENARIOS:
            raise HTTPException(status_code=400, detail=f"Unknown scenario {body.scenario!r}.")
        market_state.select_scenario(key)
    if body.primary_outage is not None:
        market_state.primary_outage = body.primary_outage
    if body.secondary_outage is not None:
        market_state.secondary_outage = body.secondary_outage
    market_service.invalidate()
    return demo_state()


# --- health --------------------------------------------------------------------


@router.get("/health", response_model=schemas.HealthOut)
def health():
    database_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        database_ok = False

    providers = market_service.health()
    degraded = not database_ok or not all(p.ok for p in providers)
    return schemas.HealthOut(
        status="degraded" if degraded else "ok",
        database=database_ok,
        cache="redis" if settings.redis_url else "memory",
        providers=[
            schemas.ProviderHealthOut(name=p.name, priority=p.priority, ok=p.ok, detail=p.detail)
            for p in providers
        ],
        scenario=market_state.scenario,
        version=APP_VERSION,
    )


@router.get("/market/status", response_model=dict)
def market_status():
    snapshot = market_service.snapshot()
    return {
        "freshness": snapshot.worst_freshness,
        "degraded": snapshot.degraded,
        "scenario": market_state.scenario,
        "scenarioLabel": synthetic.get_scenario(market_state.scenario).label,
        "capturedAt": snapshot.captured_at,
        "serverTime": datetime.now(UTC),
        "cache": "redis" if settings.redis_url else "memory",
        "cachedQuotes": len(snapshot.quotes),
    }


@router.post("/cache/purge", status_code=204)
def purge_cache(_user: CurrentUser):
    cache.delete_prefix("")
    synthetic.reset_caches()
