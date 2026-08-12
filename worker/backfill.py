"""Adaptive, resumable backfill engine.

Walks each licensed user's history in time windows so a long backfill is:
- **adaptive**: concurrency scales with the licensed-user count (bounded by
  ``INGEST_CONCURRENCY``);
- **throttle-aware**: the Graph client honours ``429`` / ``Retry-After`` and a
  semaphore applies back-pressure;
- **resumable**: a per-user ``backfill:{id}`` watermark advances per window, so a
  re-run continues where it stopped;
- **cancellable**: cooperative cancellation between windows;
- **observable**: live progress is exposed for the admin UI.
"""
from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from shared.config import settings
from shared.models import IngestState, JobRun, LicensedUser, Prompt
from shared.upsert import bulk_upsert
from shared.translations import load_translations
from worker.ingest import (
    _PROMPT_UPDATE_KEYS,
    GraphLike,
    IngestError,
    SessionFactory,
    build_graph_client,
    load_app_config,
    sync_licensed_users,
)
from worker.transforms import transform_interaction

logger = logging.getLogger("worker.backfill")

_WINDOW_DAYS = 7


@dataclass
class BackfillProgress:
    status: str = "idle"  # idle | running | completed | cancelled | failed
    users_total: int = 0
    users_done: int = 0
    prompts: int = 0
    lookback_days: int = 0
    started_at: str | None = None
    updated_at: str | None = None
    detail: str | None = None


_progress = BackfillProgress()
_cancel = asyncio.Event()


def get_progress() -> dict[str, Any]:
    return asdict(_progress)


def request_cancel() -> None:
    """Ask a running backfill to stop after the current window."""
    _cancel.set()


def is_running() -> bool:
    return _progress.status in ("running", "preparing")


def adaptive_concurrency(user_count: int, cap: int) -> int:
    """Scale concurrency with the number of users, bounded by ``cap``."""
    if user_count <= 0:
        return 1
    return max(2, min(cap, math.ceil(user_count / 4)))


def iter_windows(
    since: datetime, until: datetime, window_days: int = _WINDOW_DAYS
) -> Iterator[tuple[datetime, datetime]]:
    """Yield consecutive ``[start, end)`` windows covering ``[since, until)``."""
    if since >= until:
        return
    step = timedelta(days=window_days)
    start = since
    while start < until:
        end = min(start + step, until)
        yield start, end
        start = end


def _ensure_aware(dt: datetime) -> datetime:
    """Treat naive datetimes (e.g. from SQLite) as UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def run_backfill(
    session_factory: SessionFactory,
    *,
    graph: GraphLike | None = None,
    config: Any = None,
    lookback_days: int | None = None,
    window_days: int = _WINDOW_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Backfill Copilot prompts for all licensed users over ``lookback_days``."""
    now = now or datetime.now(timezone.utc)
    _cancel.clear()
    owns_graph = False

    async with session_factory() as session:
        if config is None:
            config = await load_app_config(session)
            if config is None or not config.tenant_id:
                raise IngestError("Graph is not configured yet.")
        if graph is None:
            graph = build_graph_client(config)
            owns_graph = True

        lookback = lookback_days or config.backfill_days
        since0 = now - timedelta(days=lookback)
        user_ids = [
            uid
            for (uid,) in (await session.execute(select(LicensedUser.user_id))).all()
        ]
        # Safety net: a backfill iterates licensed users, but only a full refresh
        # populates that list. If it's empty (typical on a brand-new instance),
        # extract the licensed users first so the backfill never silently pulls
        # nothing. The UI also offers this as an explicit step.
        if not user_ids:
            _progress.status = "preparing"
            _progress.detail = "No users yet — extracting licensed users…"
            _progress.started_at = now.isoformat()
            _progress.updated_at = datetime.now(timezone.utc).isoformat()
            await sync_licensed_users(session, graph, config)
            await session.commit()
            user_ids = [
                uid
                for (uid,) in (
                    await session.execute(select(LicensedUser.user_id))
                ).all()
            ]
        # Per-user coverage is tracked as two boundaries so a backfill can be
        # *extended further back* later: ``backfill:{id}`` = latest covered,
        # ``backfillstart:{id}`` = earliest covered. A window is skipped only
        # when it falls fully inside an already-covered [earliest, latest] span.
        covered_latest: dict[str, datetime] = {}
        covered_earliest: dict[str, datetime] = {}
        for key, wm in (
            await session.execute(
                select(IngestState.key, IngestState.watermark).where(
                    IngestState.key.like("backfill%")
                )
            )
        ).all():
            if wm is None:
                continue
            if key.startswith("backfillstart:"):
                covered_earliest[key.split(":", 1)[1]] = _ensure_aware(wm)
            elif key.startswith("backfill:"):
                covered_latest[key.split(":", 1)[1]] = _ensure_aware(wm)
        concurrency = adaptive_concurrency(len(user_ids), settings.ingest_concurrency)

        _progress.status = "running"
        _progress.users_total = len(user_ids)
        _progress.users_done = 0
        _progress.prompts = 0
        _progress.lookback_days = lookback
        _progress.started_at = now.isoformat()
        _progress.updated_at = now.isoformat()
        _progress.detail = f"concurrency={concurrency}"

        job = JobRun(job_name="backfill", status="running")
        session.add(job)
        await session.flush()

        # Load the (possibly centrally-updated) app-name translations once.
        translations = await load_translations()

        sem = asyncio.Semaphore(concurrency)
        write_lock = asyncio.Lock()
        total_prompts = 0

        async def do_user(uid: str) -> None:
            nonlocal total_prompts
            # Fill the whole requested [since0, now) range, skipping only windows
            # already fully covered by the span recorded on a PREVIOUS run. The
            # original span is held immutable for the skip test; the run's own
            # progress is tracked separately so mutating it can't collapse the gap
            # detection mid-loop.
            orig_earliest = covered_earliest.get(uid)
            orig_latest = covered_latest.get(uid)
            run_earliest = orig_earliest
            run_latest = orig_latest
            for win_start, win_end in iter_windows(since0, now, window_days):
                if _cancel.is_set():
                    return
                already_covered = (
                    orig_earliest is not None
                    and orig_latest is not None
                    and win_start >= orig_earliest
                    and win_end <= orig_latest
                )
                if already_covered:
                    continue
                async with sem:
                    rows: list[dict[str, Any]] = []
                    async for raw in graph.iter_enterprise_interactions(
                        uid, win_start, win_end
                    ):
                        row = transform_interaction(raw, uid, translations)
                        if row and row.get("prompt_id"):
                            rows.append(row)
                async with write_lock:
                    n = await bulk_upsert(
                        session,
                        Prompt,
                        rows,
                        index_elements=["prompt_id"],
                        update_keys=_PROMPT_UPDATE_KEYS,
                    )
                    # Expand the *persisted* covered span to include this window.
                    run_earliest = (
                        win_start if run_earliest is None else min(run_earliest, win_start)
                    )
                    run_latest = (
                        win_end if run_latest is None else max(run_latest, win_end)
                    )
                    await bulk_upsert(
                        session,
                        IngestState,
                        [
                            {
                                "key": f"backfill:{uid}",
                                "watermark": run_latest,
                                "last_status": "ok",
                                "last_run_at": now,
                            },
                            {
                                "key": f"backfillstart:{uid}",
                                "watermark": run_earliest,
                                "last_status": "ok",
                                "last_run_at": now,
                            },
                        ],
                        index_elements=["key"],
                        update_keys=["watermark", "last_status", "last_run_at"],
                    )
                    total_prompts += n
                    _progress.prompts = total_prompts
                    _progress.updated_at = datetime.now(timezone.utc).isoformat()
                    await session.commit()
            async with write_lock:
                _progress.users_done += 1

        try:
            await asyncio.gather(*(do_user(uid) for uid in user_ids))
            cancelled = _cancel.is_set()
            _progress.status = "cancelled" if cancelled else "completed"
            job.status = _progress.status
            stats = {
                "users": len(user_ids),
                "prompts": total_prompts,
                "lookback_days": lookback,
                "cancelled": cancelled,
            }
            job.stats = stats
            job.finished_at = datetime.now(timezone.utc)
            _progress.updated_at = job.finished_at.isoformat()
            await session.commit()
            logger.info("Backfill %s: %s", _progress.status, stats)
            return stats
        except Exception as exc:  # noqa: BLE001 - persisted for observability
            _progress.status = "failed"
            _progress.detail = str(exc)
            job.status = "failed"
            job.stats = {"error": str(exc), "prompts": total_prompts}
            job.finished_at = datetime.now(timezone.utc)
            await session.commit()
            logger.exception("Backfill failed")
            raise
        finally:
            if owns_graph and graph is not None:
                await graph.aclose()
