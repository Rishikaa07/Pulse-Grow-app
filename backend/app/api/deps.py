from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db.models import User, Watchlist
from ..db.session import get_db
from ..repositories.watchlists import WatchlistRepository
from ..services.auth import AuthService

SESSION_COOKIE = "pulse_session"

DbSession = Annotated[Session, Depends(get_db)]


def current_user(
    db: DbSession,
    pulse_session: Annotated[str | None, Cookie()] = None,
) -> User:
    user = AuthService(db).user_for(pulse_session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue."
        )
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def owned_watchlist(watchlist_id: int, db: DbSession, user: CurrentUser) -> Watchlist:
    watchlist = WatchlistRepository(db).get_owned(user.id, watchlist_id)
    if watchlist is None:
        # 404 rather than 403: do not leak the existence of other users' rows.
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    return watchlist


OwnedWatchlist = Annotated[Watchlist, Depends(owned_watchlist)]
