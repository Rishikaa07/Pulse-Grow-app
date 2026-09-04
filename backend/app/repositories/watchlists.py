from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..db.models import Watchlist, WatchlistItem


class DuplicateSymbol(Exception):
    pass


class DuplicateWatchlistName(Exception):
    pass


class WatchlistRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_user(self, user_id: int) -> list[Watchlist]:
        stmt = (
            select(Watchlist)
            .where(Watchlist.user_id == user_id)
            .options(selectinload(Watchlist.items))
            .order_by(Watchlist.position, Watchlist.id)
        )
        return list(self.db.scalars(stmt))

    def get_owned(self, user_id: int, watchlist_id: int) -> Watchlist | None:
        """Ownership is part of the query, not an afterthought in the handler."""
        stmt = (
            select(Watchlist)
            .where(Watchlist.id == watchlist_id, Watchlist.user_id == user_id)
            .options(selectinload(Watchlist.items))
        )
        return self.db.scalar(stmt)

    def create(self, user_id: int, name: str) -> Watchlist:
        position = (
            self.db.scalar(
                select(func.coalesce(func.max(Watchlist.position), -1)).where(
                    Watchlist.user_id == user_id
                )
            )
            or 0
        )
        watchlist = Watchlist(user_id=user_id, name=name.strip(), position=position + 1)
        self.db.add(watchlist)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateWatchlistName(name) from exc
        return watchlist

    def rename(self, watchlist: Watchlist, name: str) -> Watchlist:
        watchlist.name = name.strip()
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateWatchlistName(name) from exc
        return watchlist

    def delete(self, watchlist: Watchlist) -> None:
        self.db.delete(watchlist)
        self.db.flush()

    def add_symbol(self, watchlist: Watchlist, symbol: str) -> WatchlistItem:
        symbol = symbol.upper().strip()
        position = (
            self.db.scalar(
                select(func.coalesce(func.max(WatchlistItem.position), -1)).where(
                    WatchlistItem.watchlist_id == watchlist.id
                )
            )
            or 0
        )
        item = WatchlistItem(watchlist_id=watchlist.id, symbol=symbol, position=position + 1)
        self.db.add(item)
        try:
            # Two tabs clicking "add" at once resolve here, at the unique index,
            # rather than in a read-then-write race in the service layer.
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateSymbol(symbol) from exc
        return item

    def remove_symbol(self, watchlist_id: int, symbol: str) -> bool:
        item = self.db.scalar(
            select(WatchlistItem).where(
                WatchlistItem.watchlist_id == watchlist_id,
                WatchlistItem.symbol == symbol.upper().strip(),
            )
        )
        if item is None:
            return False
        self.db.delete(item)
        self.db.flush()
        return True

    def reorder(self, watchlist_id: int, symbols: list[str]) -> None:
        order = {s.upper(): i for i, s in enumerate(symbols)}
        items = list(
            self.db.scalars(
                select(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id)
            )
        )
        for item in items:
            # Symbols absent from the request keep a stable position at the end.
            item.position = order.get(item.symbol, len(order) + item.position)
        self.db.flush()

    def symbols(self, watchlist_id: int) -> list[str]:
        stmt = (
            select(WatchlistItem.symbol)
            .where(WatchlistItem.watchlist_id == watchlist_id)
            .order_by(WatchlistItem.position, WatchlistItem.id)
        )
        return list(self.db.scalars(stmt))
