"""Ingestion engine.

Ties the Graph client and pure transforms to the database. A single async
process (no Power Automate "child flow" split) fans out over licensed users with
bounded concurrency, upserts idempotently on ``prompt_id``, keeps per-user
watermarks in ``ingest_state``, and records every run in ``job_runs``.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.crypto import decrypt
from shared.models import (
    AppConfig,
    EntraUser,
    IngestState,
    JobRun,
    LicenseCount,
    LicensedUser,
    Prompt,
)
from shared.upsert import bulk_upsert
from shared.translations import load_translations
from worker.graph import GraphAuth, GraphClient
from worker.transforms import (
    has_configured_sku,
    is_included_entra_user,
    transform_entra_user,
    transform_interaction,
    transform_subscribed_sku,
)

logger = logging.getLogger("worker.ingest")

# Look-back window applied the first time a scheduled/incremental run sees a
# user (before any watermark exists). Deliberately short: deep history is the
# job of the dedicated historical backfill.
_INITIAL_INGEST_HOURS = 24

_PROMPT_UPDATE_KEYS = [
    "user_id",
    "conversation_id",
    "app_name",
    "prompt_date",
    "conversation_type",
    "conversation_location",
    "chat_type",
    "file_location",
    "teams_location",
    "raw_json",
]
_ENTRA_UPDATE_KEYS = [
    "upn",
    "email",
    "display_name",
    "job_title",
    "company_name",
    "department",
    "office_location",
    "country",
    "manager_id",
    "account_enabled",
    "user_type",
    "has_copilot_license",
    *[f"extension_attribute_{i}" for i in range(1, 16)],
]

SessionFactory = Callable[[], AsyncSession]


class IngestError(RuntimeError):
    """Raised when ingestion cannot run (e.g. Graph not configured)."""


class GraphLike(Protocol):
    """Subset of :class:`~worker.graph.GraphClient` the engine depends on."""

    def iter_licensed_users(self, sku_ids: list[str]): ...
    def get_subscribed_skus(self): ...
    def iter_directory_users(self): ...
    def iter_enterprise_interactions(
        self, user_id: str, since: datetime, until: datetime, *, page_size: int = ...
    ): ...
    async def aclose(self) -> None: ...


# --- configuration & client --------------------------------------------
async def load_app_config(session: AsyncSession) -> AppConfig | None:
    """Return the single admin-config row, or ``None`` if not yet saved."""
    return await session.get(AppConfig, 1)


def build_graph_client(config: AppConfig) -> GraphClient:
    """Construct a Graph client from stored (encrypted) credentials."""
    if not (config.tenant_id and config.client_id and config.client_secret_encrypted):
        raise IngestError("Graph credentials are not fully configured.")
    secret = decrypt(config.client_secret_encrypted)
    auth = GraphAuth(config.tenant_id, config.client_id, secret)
    return GraphClient(auth, concurrency=settings.ingest_concurrency)


# --- individual sync steps ---------------------------------------------
async def sync_licensed_users(
    session: AsyncSession, graph: GraphLike, config: AppConfig
) -> int:
    """Refresh the ``licensed_users`` snapshot from Graph."""
    rows: list[dict[str, Any]] = []
    async for user in graph.iter_licensed_users(list(config.copilot_sku_ids)):
        uid = user.get("id")
        if uid:
            rows.append({"user_id": uid})
    await session.execute(delete(LicensedUser))
    await bulk_upsert(
        session, LicensedUser, rows, index_elements=["user_id"], update_keys=[]
    )
    return len(rows)


async def sync_license_counts(
    session: AsyncSession, graph: GraphLike, config: AppConfig, now: datetime
) -> int:
    """Record today's Copilot license totals (idempotent per day)."""
    target = set(config.copilot_sku_ids)
    today = now.date()
    skus = await graph.get_subscribed_skus()
    await session.execute(
        delete(LicenseCount).where(LicenseCount.recorded_date == today)
    )
    count = 0
    for sku in skus:
        if sku.get("skuId") in target:
            session.add(LicenseCount(**transform_subscribed_sku(sku, today)))
            count += 1
    return count


async def _load_watermarks(session: AsyncSession) -> dict[str, datetime]:
    result = await session.execute(
        select(IngestState.key, IngestState.watermark).where(
            IngestState.key.like("prompt:%")
        )
    )
    return {key: wm for key, wm in result.all() if wm is not None}


async def sync_prompts(
    session: AsyncSession, graph: GraphLike, config: AppConfig, now: datetime
) -> dict[str, int]:
    """Incrementally pull Copilot prompts for every licensed user.

    Fetches run with bounded concurrency; each user resumes from its stored
    watermark (or ``backfill_days`` back on first run). Upserts are idempotent
    on ``prompt_id`` and each user's watermark advances to ``now``.
    """
    user_ids = [
        uid for (uid,) in (await session.execute(select(LicensedUser.user_id))).all()
    ]
    watermarks = await _load_watermarks(session)
    # Load the (possibly centrally-updated) app-name translations once per run.
    translations = await load_translations()
    # A scheduled/incremental run only ever looks back a short window on first
    # sight of a user (the last 24 hours). Deep history is the job of the
    # dedicated historical backfill, not the recurring ingest.
    default_since = now - timedelta(hours=_INITIAL_INGEST_HOURS)
    sem = asyncio.Semaphore(settings.ingest_concurrency)

    async def fetch(uid: str) -> tuple[str, list[dict[str, Any]]]:
        since = watermarks.get(f"prompt:{uid}", default_since)
        rows: list[dict[str, Any]] = []
        async with sem:
            async for raw in graph.iter_enterprise_interactions(uid, since, now):
                row = transform_interaction(raw, uid, translations)
                if row and row.get("prompt_id"):
                    rows.append(row)
        return uid, rows

    results = await asyncio.gather(*(fetch(uid) for uid in user_ids))

    total_prompts = 0
    for uid, rows in results:
        total_prompts += await bulk_upsert(
            session,
            Prompt,
            rows,
            index_elements=["prompt_id"],
            update_keys=_PROMPT_UPDATE_KEYS,
        )
        await bulk_upsert(
            session,
            IngestState,
            [{
                "key": f"prompt:{uid}",
                "watermark": now,
                "last_status": "ok",
                "last_run_at": now,
            }],
            index_elements=["key"],
            update_keys=["watermark", "last_status", "last_run_at"],
        )
    return {"users": len(user_ids), "prompts": total_prompts}


async def sync_entra_users(
    session: AsyncSession, graph: GraphLike, config: AppConfig
) -> int:
    """Upsert filtered directory users into ``entra_users``."""
    sku_ids = list(config.copilot_sku_ids)
    batch: list[dict[str, Any]] = []
    count = 0

    async def flush() -> int:
        nonlocal batch
        if not batch:
            return 0
        n = await bulk_upsert(
            session,
            EntraUser,
            batch,
            index_elements=["user_id"],
            update_keys=_ENTRA_UPDATE_KEYS,
        )
        batch = []
        return n

    async for user in graph.iter_directory_users():
        if not is_included_entra_user(user):
            continue
        row = transform_entra_user(
            user, has_copilot_license=has_configured_sku(user, sku_ids)
        )
        if row.get("user_id"):
            batch.append(row)
        if len(batch) >= 500:
            count += await flush()
    count += await flush()
    return count


# --- orchestrator -------------------------------------------------------
async def run_ingest(
    session_factory: SessionFactory,
    *,
    graph: GraphLike | None = None,
    config: AppConfig | None = None,
    job_name: str = "daily",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run a full ingest cycle and record it as a ``job_runs`` row.

    ``graph``/``config`` may be injected (tests); otherwise they are loaded from
    the database and built from stored credentials.
    """
    now = now or datetime.now(timezone.utc)
    owns_graph = False

    async with session_factory() as session:
        if config is None:
            config = await load_app_config(session)
            if config is None or not config.tenant_id:
                raise IngestError("Graph is not configured yet.")
        if graph is None:
            graph = build_graph_client(config)
            owns_graph = True

        job = JobRun(job_name=job_name, status="running")
        session.add(job)
        await session.flush()
        stats: dict[str, Any] = {}
        try:
            stats["licensed_users"] = await sync_licensed_users(session, graph, config)
            stats["license_counts"] = await sync_license_counts(
                session, graph, config, now
            )
            stats["prompts"] = await sync_prompts(session, graph, config, now)
            stats["entra_users"] = await sync_entra_users(session, graph, config)
            job.status = "success"
            job.finished_at = datetime.now(timezone.utc)
            job.stats = stats
            await session.commit()
            logger.info("Ingest '%s' complete: %s", job_name, stats)
            return stats
        except Exception as exc:  # noqa: BLE001 - persisted for observability
            stats["error"] = str(exc)
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
            job.stats = stats
            await session.commit()
            logger.exception("Ingest '%s' failed", job_name)
            raise
        finally:
            if owns_graph and graph is not None:
                await graph.aclose()


async def count_prompts(session: AsyncSession) -> int:
    """Convenience: total prompts currently stored."""
    return int(
        (await session.execute(select(func.count()).select_from(Prompt))).scalar_one()
    )


# --- user-only sync (fast; no prompts) ---------------------------------
# Extracting the licensed/directory user lists is a prerequisite for both the
# recurring ingest and the historical backfill (which iterate licensed users).
# This runs that step on its own so the UI can do it first — and observe it —
# before any prompt pull.
@dataclass
class UserSyncProgress:
    status: str = "idle"  # idle | running | completed | failed
    licensed_users: int = 0
    directory_users: int = 0
    updated_at: str | None = None
    detail: str | None = None


_user_sync = UserSyncProgress()


def get_user_sync_progress() -> dict[str, Any]:
    return asdict(_user_sync)


def user_sync_running() -> bool:
    return _user_sync.status == "running"


async def sync_users(
    session_factory: SessionFactory,
    *,
    graph: GraphLike | None = None,
    config: AppConfig | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Refresh only the licensed + directory user snapshots (no prompt pull).

    Recorded as a ``users`` job for observability and exposed via live progress
    so the first-run UI can extract users before a refresh/backfill.
    """
    now = now or datetime.now(timezone.utc)
    owns_graph = False
    _user_sync.status = "running"
    _user_sync.detail = "Reading licensed users…"
    _user_sync.updated_at = now.isoformat()

    async with session_factory() as session:
        if config is None:
            config = await load_app_config(session)
            if config is None or not config.tenant_id:
                _user_sync.status = "failed"
                _user_sync.detail = "Graph is not configured yet."
                _user_sync.updated_at = datetime.now(timezone.utc).isoformat()
                raise IngestError("Graph is not configured yet.")
        if graph is None:
            graph = build_graph_client(config)
            owns_graph = True

        job = JobRun(job_name="users", status="running")
        session.add(job)
        await session.flush()
        stats: dict[str, Any] = {}
        try:
            stats["licensed_users"] = await sync_licensed_users(session, graph, config)
            _user_sync.licensed_users = stats["licensed_users"]
            _user_sync.detail = "Recording licence totals…"
            _user_sync.updated_at = datetime.now(timezone.utc).isoformat()

            stats["license_counts"] = await sync_license_counts(
                session, graph, config, now
            )
            _user_sync.detail = "Reading directory users…"
            _user_sync.updated_at = datetime.now(timezone.utc).isoformat()

            stats["entra_users"] = await sync_entra_users(session, graph, config)
            _user_sync.directory_users = stats["entra_users"]

            job.status = "success"
            job.finished_at = datetime.now(timezone.utc)
            job.stats = stats
            await session.commit()
            _user_sync.status = "completed"
            _user_sync.detail = None
            _user_sync.updated_at = job.finished_at.isoformat()
            logger.info("User sync complete: %s", stats)
            return stats
        except Exception as exc:  # noqa: BLE001 - persisted for observability
            stats["error"] = str(exc)
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
            job.stats = stats
            await session.commit()
            _user_sync.status = "failed"
            _user_sync.detail = str(exc)
            _user_sync.updated_at = job.finished_at.isoformat()
            logger.exception("User sync failed")
            raise
        finally:
            if owns_graph and graph is not None:
                await graph.aclose()


async def test_graph_connection(config: AppConfig) -> dict[str, Any]:
    """Validate stored Graph credentials and permissions with light calls.

    Acquires a token, reads ``subscribedSkus`` (Directory.Read.All) and counts
    Copilot-licensed users. Never raises: failures are reported in the result.
    """
    result: dict[str, Any] = {
        "ok": False,
        "token_acquired": False,
        "subscribed_skus": False,
        "directory_read": False,
        "copilot_licensed_users": None,
        "detail": None,
    }
    try:
        graph = build_graph_client(config)
    except IngestError as exc:
        result["detail"] = str(exc)
        return result
    try:
        await graph.acquire_token()
        result["token_acquired"] = True
        await graph.get_subscribed_skus()
        result["subscribed_skus"] = True
        count = 0
        async for _ in graph.iter_licensed_users(list(config.copilot_sku_ids)):
            count += 1
        result["copilot_licensed_users"] = count
        result["directory_read"] = True
        result["ok"] = True
    except Exception as exc:  # noqa: BLE001 - reported to caller
        result["detail"] = str(exc)
    finally:
        await graph.aclose()
    return result
