"""Seeding.

A brand-new account with an empty watchlist cannot demonstrate anything, so a
first sign-in gets a spread across sectors — enough breadth for the relative
signals to say something, and small enough to stay legible.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.models import User
from ..providers import universe
from ..repositories.watchlists import DuplicateSymbol, WatchlistRepository

STARTER_NAME = "Core"
STARTER_SYMBOLS = (
    "NVDA",
    "AMD",
    "TSM",
    "AAPL",
    "MSFT",
    "GOOGL",
    "TSLA",
    "AMZN",
    "JPM",
    "XOM",
    "LLY",
    "COST",
)

SECONDARY_NAME = "Semis only"
SECONDARY_SYMBOLS = ("NVDA", "AMD", "AVGO", "INTC", "TSM")


def ensure_starter_watchlist(db: Session, user: User) -> None:
    """Idempotent: safe to call on every login."""
    repo = WatchlistRepository(db)
    if repo.list_for_user(user.id):
        return

    for name, symbols in ((STARTER_NAME, STARTER_SYMBOLS), (SECONDARY_NAME, SECONDARY_SYMBOLS)):
        watchlist = repo.create(user.id, name)
        for symbol in symbols:
            if not universe.exists(symbol):
                continue
            try:
                repo.add_symbol(watchlist, symbol)
            except DuplicateSymbol:
                continue
