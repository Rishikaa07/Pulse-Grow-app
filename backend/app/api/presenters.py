"""Domain → wire mapping.

Kept apart from both the services and the routes so that changing the shape of
the JSON never means editing business logic.
"""

from __future__ import annotations

from ..db.models import Watchlist
from ..providers import universe
from ..services.overview import Overview, ScoredItem
from . import schemas


def watchlist_out(watchlist: Watchlist) -> schemas.WatchlistOut:
    items = sorted(watchlist.items, key=lambda i: (i.position, i.id))
    return schemas.WatchlistOut(
        id=watchlist.id,
        name=watchlist.name,
        position=watchlist.position,
        item_count=len(items),
        items=[
            schemas.WatchlistItemOut(
                symbol=item.symbol,
                name=(inst.name if (inst := universe.get(item.symbol)) else item.symbol),
                sector=universe.sector_label(inst.sector) if inst else "Unclassified",
                position=item.position,
            )
            for item in items
        ],
    )


def attention_item_out(item: ScoredItem) -> schemas.AttentionItemOut:
    r = item.result
    return schemas.AttentionItemOut(
        symbol=r.symbol,
        name=r.name,
        attention_score=r.attention_score,
        severity=str(r.severity),
        headline=r.headline,
        explanation=r.explanation,
        price=r.price,
        changes=schemas.ChangesOut(
            since_visit_pct=r.change_since_visit_pct,
            today_pct=r.change_today_pct,
            week_pct=r.change_week_pct,
        ),
        benchmarks=schemas.BenchmarksOut(
            sector_code=item.sector_code,
            sector_label=item.sector_label,
            sector_change_pct=r.sector_change_pct,
            market_change_pct=r.market_change_pct,
            relative_edge_pct=r.relative_edge_pct,
        ),
        baseline=schemas.BaselineOut(
            price=r.baseline.price,
            observed_at=r.baseline.observed_at,
            source=r.baseline.source,
        ),
        signals=[
            schemas.SignalOut(
                type=str(s.type),
                value=s.value,
                display=s.display,
                weight=s.weight,
                contribution=s.contribution,
                detail=s.detail,
            )
            for s in r.signals
        ],
        confidence=schemas.ConfidenceOut(
            level=str(r.confidence.level),
            score=r.confidence.score,
            reasons=r.confidence.reasons,
        ),
        freshness=schemas.FreshnessOut(
            state=r.freshness,
            age_seconds=round(r.data_age_seconds, 1),
            source="",
            as_of=r.as_of,
            notes=[],
        ),
        volume_ratio=r.volume_ratio,
        sigma_multiple=r.sigma_multiple,
        changed_since_last_visit=r.changed_since_last_visit,
        events=[
            schemas.EventOut(
                id=e.id, headline=e.headline, kind=e.kind, occurred_at=e.occurred_at
            )
            for e in r.events
        ],
        status=item.status,
        change_event_id=item.change_event_id,
        fingerprint=r.fingerprint,
    )


def overview_out(overview: Overview, scenario: str) -> schemas.OverviewOut:
    snapshot = overview.snapshot
    items = [attention_item_out(item) for item in overview.items]

    # Attach provenance per item from the reconciled quote.
    for out in items:
        quote = snapshot.quotes.get(out.symbol)
        if quote is not None:
            out.freshness.source = quote.quality.selected_source
            out.freshness.notes = list(quote.quality.notes)

    return schemas.OverviewOut(
        watchlist=watchlist_out(overview.watchlist),
        visit=schemas.VisitOut(
            started_at=overview.visit.started_at,
            is_new_visit=overview.visit.is_new_visit,
            last_visit_at=overview.visit.last_visit_at,
            away_seconds=overview.visit.away_seconds,
            baseline_source=overview.visit.baseline_source,
        ),
        summary=schemas.SummaryOut(
            tracked=overview.summary.tracked,
            meaningful_changes=overview.summary.meaningful_changes,
            unusual_moves=overview.summary.unusual_moves,
            events=overview.summary.events,
            quiet=overview.summary.quiet,
            new_in_inbox=overview.summary.new_in_inbox,
        ),
        items=items,
        indices=[
            schemas.IndexOut(
                key=index.key,
                label=index.label,
                change_today_pct=round(index.change_today_pct, 4),
            )
            for index in sorted(snapshot.indices.values(), key=lambda i: i.label)
        ],
        data_quality=schemas.DataQualityOut(
            freshness=snapshot.worst_freshness,
            degraded=snapshot.degraded,
            providers=[
                schemas.ProviderHealthOut(
                    name=h.name, priority=h.priority, ok=h.ok, detail=h.detail
                )
                for h in snapshot.provider_health
            ],
            discrepancies=[
                f"{d.symbol}: feeds differ by {d.deviation_pct:.2f}%, using {d.primary_source}"
                for d in snapshot.discrepancies
            ],
            missing_symbols=snapshot.missing,
        ),
        scenario=scenario,
        generated_at=overview.generated_at,
    )
