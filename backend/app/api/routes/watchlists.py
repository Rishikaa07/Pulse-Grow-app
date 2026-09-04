from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ...config import settings
from ...providers import universe
from ...providers.mock import market_state
from ...repositories.events import STATUS_NEW, ChangeEventRepository
from ...repositories.snapshots import VisitRepository
from ...repositories.watchlists import (
    DuplicateSymbol,
    DuplicateWatchlistName,
    WatchlistRepository,
)
from ...services.overview import OverviewService
from .. import presenters, schemas
from ..deps import CurrentUser, DbSession, OwnedWatchlist

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@router.get("", response_model=list[schemas.WatchlistOut])
def list_watchlists(db: DbSession, user: CurrentUser):
    return [presenters.watchlist_out(w) for w in WatchlistRepository(db).list_for_user(user.id)]


@router.post("", response_model=schemas.WatchlistOut, status_code=201)
def create_watchlist(body: schemas.WatchlistCreate, db: DbSession, user: CurrentUser):
    repo = WatchlistRepository(db)
    try:
        watchlist = repo.create(user.id, body.name)
        for symbol in dict.fromkeys(s.upper().strip() for s in body.symbols):
            if universe.exists(symbol):
                repo.add_symbol(watchlist, symbol)
    except DuplicateWatchlistName as exc:
        raise HTTPException(status_code=409, detail="You already have a list with that name.") from exc
    except DuplicateSymbol:
        pass
    db.commit()
    db.refresh(watchlist)
    return presenters.watchlist_out(watchlist)


@router.patch("/{watchlist_id}", response_model=schemas.WatchlistOut)
def rename_watchlist(body: schemas.WatchlistUpdate, db: DbSession, watchlist: OwnedWatchlist):
    try:
        WatchlistRepository(db).rename(watchlist, body.name)
    except DuplicateWatchlistName as exc:
        raise HTTPException(status_code=409, detail="You already have a list with that name.") from exc
    db.commit()
    db.refresh(watchlist)
    return presenters.watchlist_out(watchlist)


@router.delete("/{watchlist_id}", status_code=204)
def delete_watchlist(db: DbSession, user: CurrentUser, watchlist: OwnedWatchlist):
    repo = WatchlistRepository(db)
    if len(repo.list_for_user(user.id)) <= 1:
        raise HTTPException(status_code=409, detail="Keep at least one watchlist.")
    repo.delete(watchlist)
    db.commit()


@router.post("/{watchlist_id}/stocks", response_model=schemas.WatchlistOut, status_code=201)
def add_stock(body: schemas.SymbolField, db: DbSession, watchlist: OwnedWatchlist):
    if not universe.exists(body.symbol):
        raise HTTPException(status_code=404, detail=f"{body.symbol} is not a symbol we track.")
    if len(watchlist.items) >= settings.max_symbols_per_watchlist:
        raise HTTPException(
            status_code=409,
            detail=f"A watchlist holds up to {settings.max_symbols_per_watchlist} symbols.",
        )
    try:
        WatchlistRepository(db).add_symbol(watchlist, body.symbol)
    except DuplicateSymbol as exc:
        raise HTTPException(status_code=409, detail=f"{body.symbol} is already on this list.") from exc
    db.commit()
    db.refresh(watchlist)
    return presenters.watchlist_out(watchlist)


@router.delete("/{watchlist_id}/stocks/{symbol}", response_model=schemas.WatchlistOut)
def remove_stock(symbol: str, db: DbSession, watchlist: OwnedWatchlist):
    if not WatchlistRepository(db).remove_symbol(watchlist.id, symbol):
        raise HTTPException(status_code=404, detail=f"{symbol.upper()} is not on this list.")
    db.commit()
    db.refresh(watchlist)
    return presenters.watchlist_out(watchlist)


@router.post("/{watchlist_id}/reorder", response_model=schemas.WatchlistOut)
def reorder(body: schemas.ReorderRequest, db: DbSession, watchlist: OwnedWatchlist):
    WatchlistRepository(db).reorder(watchlist.id, body.symbols)
    db.commit()
    db.refresh(watchlist)
    return presenters.watchlist_out(watchlist)


@router.get("/{watchlist_id}/overview", response_model=schemas.OverviewOut)
def overview(db: DbSession, user: CurrentUser, watchlist: OwnedWatchlist):
    """The main screen. Everything the dashboard needs in one round trip."""
    result = OverviewService(db).build(user, watchlist)
    db.commit()
    return presenters.overview_out(result, market_state.scenario)


@router.get("/{watchlist_id}/changes", response_model=list[schemas.ChangeEventOut])
def changes(
    db: DbSession,
    watchlist: OwnedWatchlist,
    status: str | None = Query(default=None, pattern="^(new|reviewed|dismissed)$"),
    limit: int = Query(default=50, ge=1, le=200),
):
    statuses = {status} if status else None
    return ChangeEventRepository(db).feed(watchlist.id, statuses, limit)


@router.post("/{watchlist_id}/changes/review-all", response_model=schemas.SummaryOut)
def review_all(db: DbSession, user: CurrentUser, watchlist: OwnedWatchlist):
    repo = ChangeEventRepository(db)
    repo.mark_all(watchlist.id, user.id)
    db.commit()
    return schemas.SummaryOut(
        tracked=len(watchlist.items),
        meaningful_changes=0,
        unusual_moves=0,
        events=0,
        quiet=len(watchlist.items),
        new_in_inbox=repo.count_new(watchlist.id),
    )


@router.post("/{watchlist_id}/baseline/reset", status_code=204)
def reset_baseline(db: DbSession, user: CurrentUser, watchlist: OwnedWatchlist):
    """Start a fresh visit: "everything from here on is new to me"."""
    VisitRepository(db).close_current(user.id, watchlist.id)
    ChangeEventRepository(db).mark_all(watchlist.id, user.id)
    db.commit()


@router.get("/{watchlist_id}/inbox-count", response_model=dict)
def inbox_count(db: DbSession, watchlist: OwnedWatchlist):
    repo = ChangeEventRepository(db)
    return {"new": repo.count_new(watchlist.id), "status": STATUS_NEW}
