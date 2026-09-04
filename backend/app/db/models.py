"""Persistence model.

Notes on the parts that carry real weight:

*   `Visit` is what makes "since your last check" honest. Polling inside one
    visit must not move the baseline, so observations are keyed by visit and the
    baseline for the current visit is the last thing the *previous* visit saw.
*   `ChangeEvent.fingerprint` is uniquely constrained per watchlist so that a
    background job running every 30 seconds cannot fill the inbox with 120
    copies of the same move.
*   Uniqueness on `(watchlist_id, symbol)` makes duplicate watchlist entries a
    database-level impossibility rather than a race the API hopes to win.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Per-user attention weight overrides, validated through AttentionWeights.
    attention_profile: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    watchlists: Mapped[list["Watchlist"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Watchlist(Base, TimestampMixin):
    __tablename__ = "watchlists"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_watchlist_user_name"),
        Index("ix_watchlists_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped[User] = relationship(back_populates="watchlists")
    items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="watchlist",
        cascade="all, delete-orphan",
        order_by="WatchlistItem.position",
    )


class WatchlistItem(Base, TimestampMixin):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_symbol"),
        Index("ix_watchlist_items_symbol", "symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(12), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    watchlist: Mapped[Watchlist] = relationship(back_populates="items")


class Visit(Base):
    """One continuous period of the user looking at a watchlist."""

    __tablename__ = "visits"
    __table_args__ = (
        Index("ix_visits_user_watchlist_seen", "user_id", "watchlist_id", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class UserSnapshot(Base):
    """What the user actually saw, per symbol, during a visit."""

    __tablename__ = "user_snapshots"
    __table_args__ = (
        UniqueConstraint("visit_id", "symbol", name="uq_snapshot_visit_symbol"),
        Index("ix_user_snapshots_lookup", "user_id", "watchlist_id", "symbol", "observed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    visit_id: Mapped[int] = mapped_column(
        ForeignKey("visits.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(12), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class MarketSnapshot(Base):
    """Periodic tape archive. Shared across all users — never per-user."""

    __tablename__ = "market_snapshots"
    __table_args__ = (
        Index("ix_market_snapshots_symbol_ts", "symbol", "captured_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(12), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )


class ChangeEvent(Base):
    """A change the engine judged worth telling the user about."""

    __tablename__ = "change_events"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "fingerprint", name="uq_change_fingerprint"),
        Index("ix_change_events_feed", "watchlist_id", "status", "detected_at"),
        Index("ix_change_events_symbol", "symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(12), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(40), nullable=False)

    attention_score: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    headline: Mapped[str] = mapped_column(String(200), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    signals: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)

    status: Mapped[str] = mapped_column(String(16), default="new", nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EventReview(Base):
    """Audit trail of inbox state transitions."""

    __tablename__ = "event_reviews"
    __table_args__ = (Index("ix_event_reviews_event", "change_event_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    change_event_id: Mapped[int] = mapped_column(
        ForeignKey("change_events.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str] = mapped_column(String(16), nullable=False)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class DataQualityLog(Base):
    """Every time the feeds disagreed or a provider let us down."""

    __tablename__ = "data_quality_logs"
    __table_args__ = (Index("ix_data_quality_symbol_ts", "symbol", "detected_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str | None] = mapped_column(String(12), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # discrepancy | outage | stale
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
