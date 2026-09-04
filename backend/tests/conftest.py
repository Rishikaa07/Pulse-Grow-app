"""Shared test setup.

Environment must be configured before `app.config` is imported, because
settings are read once and cached. Doing it here rather than in each test
module also means every module talks to the same, deliberately chosen database
instead of racing to set the variable first.
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("PULSE_SECRET_KEY", "test-key")
_fd, _path = tempfile.mkstemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_path}"

import pytest  # noqa: E402

from app.providers import synthetic  # noqa: E402
from app.providers.mock import market_state  # noqa: E402
from app.services.market import market_service  # noqa: E402


@pytest.fixture(autouse=True)
def reset_market_state():
    """The tape is a process-wide singleton, so hand each test a clean one."""
    yield
    market_state.primary_outage = False
    market_state.secondary_outage = False
    market_state.select_scenario(synthetic.DEFAULT_SCENARIO)
    market_service.invalidate()
