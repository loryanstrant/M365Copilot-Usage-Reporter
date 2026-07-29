"""Dialect-aware bulk upsert helper.

Uses ``INSERT ... ON CONFLICT DO UPDATE`` on both PostgreSQL (production) and
SQLite (test-suite), so ingestion is idempotent regardless of backend.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import engine

_CHUNK = 500


def _insert():
    return pg_insert if engine.dialect.name == "postgresql" else sqlite_insert


def _dedupe(
    rows: Sequence[dict[str, Any]], keys: list[str]
) -> list[dict[str, Any]]:
    """Collapse rows sharing the same conflict key (last occurrence wins).

    ``INSERT ... ON CONFLICT DO UPDATE`` fails if a single statement targets the
    same conflict key twice ("cannot affect row a second time"), which happens
    when Graph returns a duplicate interaction within one batch.
    """
    seen: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        seen[tuple(row.get(k) for k in keys)] = row
    return list(seen.values())


async def bulk_upsert(
    session: AsyncSession,
    model: Any,
    rows: Sequence[dict[str, Any]],
    *,
    index_elements: list[str],
    update_keys: list[str] | None = None,
) -> int:
    """Insert ``rows`` for ``model``, updating ``update_keys`` on conflict.

    When ``update_keys`` is empty the conflict is ignored (pure idempotency).
    Rows are de-duplicated on ``index_elements`` first. Returns the number of
    (de-duplicated) rows submitted.
    """
    rows = [r for r in rows if r]
    if not rows:
        return 0
    rows = _dedupe(rows, index_elements)

    insert = _insert()
    submitted = 0
    for start in range(0, len(rows), _CHUNK):
        chunk = rows[start:start + _CHUNK]
        stmt = insert(model).values(chunk)
        if update_keys:
            stmt = stmt.on_conflict_do_update(
                index_elements=index_elements,
                set_={k: getattr(stmt.excluded, k) for k in update_keys},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=index_elements)
        await session.execute(stmt)
        submitted += len(chunk)
    return submitted
