"""Schedule + first-run-window behaviour (Phase: friendly schedule)."""
from __future__ import annotations

from worker.ingest import _INITIAL_INGEST_HOURS
from worker.main import clamp_interval_hours


def test_clamp_interval_hours():
    assert clamp_interval_hours(None) == 24  # default = daily
    assert clamp_interval_hours(0) == 24  # invalid -> default
    assert clamp_interval_hours(-5) == 24  # negative -> default
    assert clamp_interval_hours(1) == 1  # hourly is the floor
    assert clamp_interval_hours(6) == 6
    assert clamp_interval_hours(24) == 24
    assert clamp_interval_hours(48) == 24  # never less often than daily


def test_initial_ingest_window_is_24h():
    # A scheduled/incremental first run only looks back one day.
    assert _INITIAL_INGEST_HOURS == 24
