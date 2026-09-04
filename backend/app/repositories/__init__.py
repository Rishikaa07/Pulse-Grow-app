"""Repositories.

Services describe intent; repositories know about tables. Keeping the split
means the attention engine and the overview service never grow a `session`
argument, and the query patterns stay in one place where their indexes are
obvious.
"""

from .events import ChangeEventRepository, DataQualityRepository
from .snapshots import MarketSnapshotRepository, VisitRepository
from .users import UserRepository
from .watchlists import WatchlistRepository

__all__ = [
    "ChangeEventRepository",
    "DataQualityRepository",
    "MarketSnapshotRepository",
    "UserRepository",
    "VisitRepository",
    "WatchlistRepository",
]
