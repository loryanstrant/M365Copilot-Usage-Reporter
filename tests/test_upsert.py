"""Tests for the dialect-aware bulk upsert (dedupe + idempotency)."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from shared.models import Prompt
from shared.upsert import bulk_upsert

_KEYS = ["prompt_id"]
_UPDATE = ["app_name"]


def _row(pid: str, app: str) -> dict:
    return {"prompt_id": pid, "user_id": "u1", "app_name": app}


@pytest.mark.asyncio
async def test_dedupes_duplicate_conflict_keys_in_one_batch(session):
    # Two rows with the same prompt_id must not raise "cannot affect row twice".
    n = await bulk_upsert(
        session,
        Prompt,
        [_row("p1", "A"), _row("p1", "B"), _row("p2", "C")],
        index_elements=_KEYS,
        update_keys=_UPDATE,
    )
    await session.commit()
    assert n == 2  # de-duplicated
    total = (await session.execute(select(func.count()).select_from(Prompt))).scalar_one()
    assert total == 2
    # Last occurrence wins for the duplicated key.
    app = await session.scalar(select(Prompt.app_name).where(Prompt.prompt_id == "p1"))
    assert app == "B"


@pytest.mark.asyncio
async def test_upsert_is_idempotent_across_calls(session):
    await bulk_upsert(session, Prompt, [_row("p1", "A")], index_elements=_KEYS, update_keys=_UPDATE)
    await bulk_upsert(session, Prompt, [_row("p1", "Z")], index_elements=_KEYS, update_keys=_UPDATE)
    await session.commit()
    total = (await session.execute(select(func.count()).select_from(Prompt))).scalar_one()
    assert total == 1
    app = await session.scalar(select(Prompt.app_name).where(Prompt.prompt_id == "p1"))
    assert app == "Z"


@pytest.mark.asyncio
async def test_empty_rows_noop(session):
    assert await bulk_upsert(session, Prompt, [], index_elements=_KEYS) == 0
