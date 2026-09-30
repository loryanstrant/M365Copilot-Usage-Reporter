"""Scan history — the run log job_runs has always recorded and never showed.

The interesting part is that neither vocabulary is tidy. Five job_name values
exist across the code and production, and six statuses, two of which mean the
same thing. The display layer absorbs that, and these tests pin it so a future
change cannot quietly start dropping runs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from api import metrics
from shared.db import SessionLocal
from shared.models import JobRun

T0 = datetime(2026, 9, 30, 6, 0, tzinfo=timezone.utc)


async def _run(name: str, status: str, *, minutes: int = 1, stats=None, offset=0):
    async with SessionLocal() as s:
        s.add(
            JobRun(
                job_name=name,
                status=status,
                started_at=T0 - timedelta(hours=offset),
                finished_at=T0 - timedelta(hours=offset) + timedelta(minutes=minutes),
                stats=stats,
            )
        )
        await s.commit()


async def _history():
    async with SessionLocal() as s:
        return await metrics.scan_history(s)


@pytest.mark.asyncio
async def test_every_job_name_the_code_writes_is_labelled():
    """daily, manual, users, backfill — plus scheduled, which production holds."""
    for n in ("daily", "manual", "users", "backfill", "scheduled"):
        await _run(n, "success")
    labels = {r["raw_kind"]: r["kind"] for r in await _history()}
    assert labels["daily"] == "Scheduled"
    assert labels["scheduled"] == "Scheduled"
    assert labels["manual"] == "Manual"
    assert labels["users"] == "User sync"
    assert labels["backfill"] == "Historical backfill"


@pytest.mark.asyncio
async def test_an_unknown_kind_is_shown_not_dropped():
    """A run that happened and is not listed is worse than one labelled oddly."""
    await _run("something-new", "success")
    rows = await _history()
    assert len(rows) == 1
    assert rows[0]["kind"] == "something-new"


@pytest.mark.asyncio
async def test_success_and_completed_are_one_state():
    """They differ only by which module wrote the row."""
    await _run("daily", "success")
    await _run("backfill", "completed", offset=1)
    assert {r["state"] for r in await _history()} == {"succeeded"}


@pytest.mark.asyncio
async def test_the_other_statuses_map_to_three_states():
    await _run("daily", "running")
    await _run("daily", "preparing", offset=1)
    await _run("daily", "failed", offset=2)
    await _run("daily", "cancelled", offset=3)
    states = [r["state"] for r in await _history()]
    assert states == ["running", "running", "failed", "cancelled"]


@pytest.mark.asyncio
async def test_a_failed_run_surfaces_its_error():
    await _run("daily", "failed", stats={"error": "AADSTS7000215: invalid client secret"})
    rows = await _history()
    assert "AADSTS7000215" in rows[0]["error"]
    # and the error is not repeated inside the stats blob shown beside it
    assert "error" not in rows[0]["stats"]


@pytest.mark.asyncio
async def test_duration_is_reported_and_newest_is_first():
    await _run("daily", "success", minutes=2, offset=0)
    await _run("manual", "success", minutes=9, offset=5)
    rows = await _history()
    assert rows[0]["raw_kind"] == "daily"
    assert rows[0]["duration_seconds"] == 120
    assert rows[1]["duration_seconds"] == 540


@pytest.mark.asyncio
async def test_a_run_still_in_flight_has_no_duration():
    async with SessionLocal() as s:
        s.add(JobRun(job_name="daily", status="running", started_at=T0))
        await s.commit()
    assert (await _history())[0]["duration_seconds"] is None
