"""Backfill engine tests: windowing, adaptive concurrency, resumability."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from shared.db import SessionLocal
from shared.models import AppConfig, IngestState, LicensedUser, Prompt
from worker.backfill import adaptive_concurrency, iter_windows, run_backfill

NOW = datetime(2026, 7, 29, tzinfo=timezone.utc)
SKU = "639dec6b-bb19-468b-871c-c5c441c4b0cb"


def test_adaptive_concurrency():
    assert adaptive_concurrency(0, 15) == 1
    assert adaptive_concurrency(5, 15) == 2
    assert adaptive_concurrency(100, 15) == 15  # capped
    assert adaptive_concurrency(20, 15) == 5


def test_iter_windows_splits_range():
    since = datetime(2026, 7, 1, tzinfo=timezone.utc)
    until = datetime(2026, 7, 15, tzinfo=timezone.utc)
    windows = list(iter_windows(since, until, window_days=7))
    assert len(windows) == 2
    assert windows[0][0] == since
    assert windows[-1][1] == until


def test_iter_windows_empty_when_reversed():
    d = datetime(2026, 7, 15, tzinfo=timezone.utc)
    assert list(iter_windows(d, d)) == []


class FakeGraph:
    def __init__(self, interactions_by_user):
        self._by_user = interactions_by_user

    async def iter_enterprise_interactions(self, user_id, since, until, *, page_size=100):
        for raw in self._by_user.get(user_id, []):
            dt = datetime.fromisoformat(raw["createdDateTime"].replace("Z", "+00:00"))
            if since <= dt < until:
                yield raw

    async def aclose(self):
        pass


def _config() -> AppConfig:
    return AppConfig(
        id=1, tenant_id="t", client_id="c", client_secret_encrypted="x",
        copilot_sku_ids=[SKU], backfill_days=30,
    )


def _interaction(pid: str, iso: str) -> dict:
    return {
        "id": pid,
        "sessionId": "conv",
        "appClass": "BizChat",
        "conversationType": "bizchat",
        "createdDateTime": iso,
        "contexts": [],
    }


@pytest.fixture
async def licensed(session):
    session.add(LicensedUser(user_id="user-1"))
    await session.commit()


@pytest.mark.asyncio
async def test_backfill_ingests_all_windows(licensed):
    graph = FakeGraph(
        {
            "user-1": [
                _interaction("p1", "2026-07-01T10:00:00Z"),
                _interaction("p2", "2026-07-15T10:00:00Z"),
                _interaction("p3", "2026-07-28T10:00:00Z"),
            ]
        }
    )
    stats = await run_backfill(
        SessionLocal, graph=graph, config=_config(), lookback_days=30, now=NOW
    )
    assert stats["prompts"] == 3
    assert stats["cancelled"] is False

    async with SessionLocal() as s:
        total = (await s.execute(select(func.count()).select_from(Prompt))).scalar_one()
        assert total == 3
        wm = await s.scalar(
            select(IngestState.watermark).where(IngestState.key == "backfill:user-1")
        )
        assert wm is not None


@pytest.mark.asyncio
async def test_backfill_skips_already_covered_span(session, licensed):
    # Pre-seed a fully-covered span [2026-07-01, now]. A re-run of the same
    # lookback should skip those windows entirely.
    session.add_all(
        [
            IngestState(
                key="backfillstart:user-1",
                watermark=datetime(2026, 7, 1, tzinfo=timezone.utc),
                last_status="ok",
            ),
            IngestState(
                key="backfill:user-1",
                watermark=NOW,
                last_status="ok",
            ),
        ]
    )
    await session.commit()

    graph = FakeGraph(
        {"user-1": [_interaction("p3", "2026-07-28T10:00:00Z")]}  # inside covered span
    )
    stats = await run_backfill(
        SessionLocal, graph=graph, config=_config(), lookback_days=30, now=NOW
    )
    assert stats["prompts"] == 0  # nothing fetched; span already covered


@pytest.mark.asyncio
async def test_backfill_extends_further_back(session, licensed):
    # Regression: a previous short backfill covered [2026-07-01, now]. Asking for
    # a *longer* lookback must fill the earlier gap, not no-op on the forward
    # watermark (the original bug).
    session.add_all(
        [
            IngestState(
                key="backfillstart:user-1",
                watermark=datetime(2026, 7, 1, tzinfo=timezone.utc),
                last_status="ok",
            ),
            IngestState(
                key="backfill:user-1",
                watermark=NOW,
                last_status="ok",
            ),
        ]
    )
    await session.commit()

    graph = FakeGraph(
        {
            "user-1": [
                _interaction("p0", "2026-06-10T10:00:00Z"),  # in the earlier gap
                _interaction("p3", "2026-07-28T10:00:00Z"),  # already covered
            ]
        }
    )
    stats = await run_backfill(
        SessionLocal, graph=graph, config=_config(), lookback_days=60, now=NOW
    )
    assert stats["prompts"] == 1  # only the gap interaction p0

    async with SessionLocal() as s:
        ids = {pid for (pid,) in (await s.execute(select(Prompt.prompt_id))).all()}
        assert ids == {"p0"}
