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
from shared.translations import load_translations
from shared.upsert import bulk_upsert
from worker.graph import GraphAuth, GraphClient
from worker.licensing import (
    copilot_granting_skus,
    describe_granting_skus,
    has_copilot_license,
)
from worker.transforms import (
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
async def resolve_granting_skus(graph: GraphLike, config: AppConfig) -> set[str]:
    """Which of the tenant's SKUs grant Copilot.

    Asks the tenant rather than matching a hard-coded list, so E7 and any
    future Copilot-bearing SKU are covered without a code change. The stored
    ``copilot_sku_ids`` is honoured as a manual override when set.
    """
    skus = await graph.get_subscribed_skus()
    return copilot_granting_skus(skus, override=list(config.copilot_sku_ids or []))


async def sync_licensed_users(
    session: AsyncSession,
    graph: GraphLike,
    config: AppConfig,
    granting_skus: set[str] | None = None,
) -> int:
    """Refresh the ``licensed_users`` snapshot from Graph."""
    if granting_skus is None:
        granting_skus = await resolve_granting_skus(graph, config)
    if not granting_skus:
        # Nothing in this tenant grants Copilot, so nobody is licensed. Say so
        # by clearing the table rather than leaving yesterday's answer behind.
        await session.execute(delete(LicensedUser))
        return 0
    rows: list[dict[str, Any]] = []
    async for user in graph.iter_licensed_users(sorted(granting_skus)):
        # The Graph filter matches the SKU; it cannot express "and the Copilot
        # plan is not disabled for this person", so that is checked here.
        if not has_copilot_license(user, granting_skus):
            continue
        uid = user.get("id")
        if uid:
            rows.append({"user_id": uid})
    await session.execute(delete(LicensedUser))
    await bulk_upsert(
        session, LicensedUser, rows, index_elements=["user_id"], update_keys=[]
    )
    return len(rows)


async def sync_license_counts(
    session: AsyncSession,
    graph: GraphLike,
    config: AppConfig,
    now: datetime,
    granting_skus: set[str] | None = None,
) -> int:
    """Record today's Copilot license totals (idempotent per day).

    More than one SKU can grant Copilot, so this writes a row per granting
    subscription and callers must aggregate rather than assume a single row.
    """
    today = now.date()
    skus = await graph.get_subscribed_skus()
    target = (
        granting_skus
        if granting_skus is not None
        else copilot_granting_skus(skus, override=list(config.copilot_sku_ids or []))
    )
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
    session: AsyncSession,
    graph: GraphLike,
    config: AppConfig,
    granting_skus: set[str] | None = None,
) -> int:
    """Upsert filtered directory users into ``entra_users``."""
    if granting_skus is None:
        granting_skus = await resolve_granting_skus(graph, config)
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
            user, has_copilot_license=has_copilot_license(user, granting_skus)
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
            # Resolved once and threaded through: every step needs the same
            # answer, and subscribedSkus is a per-tenant fact, not a per-step one.
            granting = await resolve_granting_skus(graph, config)
            stats["copilot_skus"] = len(granting)
            stats["licensed_users"] = await sync_licensed_users(
                session, graph, config, granting
            )
            stats["license_counts"] = await sync_license_counts(
                session, graph, config, now, granting
            )
            stats["prompts"] = await sync_prompts(session, graph, config, now)
            stats["entra_users"] = await sync_entra_users(
                session, graph, config, granting
            )
            # Real data has arrived, so the demo persona the password admin was
            # borrowing is now misleading — it would keep showing a fictional
            # person's activity as "your" usage. Retire it here rather than
            # relying on someone remembering to press Clear demo data.
            cfg_row = await session.get(AppConfig, 1)
            if cfg_row is not None:
                cfg_row.demo_persona_user_id = None
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


def _mark_user_sync_failed(detail: str) -> None:
    """Record a failed user sync and release the "running" flag.

    Only the first failure wins: a re-raise passing back out through an outer
    handler must not overwrite the real reason with a vaguer one.
    """
    if _user_sync.status != "running":
        return
    _user_sync.status = "failed"
    _user_sync.detail = detail
    _user_sync.updated_at = datetime.now(timezone.utc).isoformat()


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
    owns_graph = False

    # Nothing between raising the flag and the guard. `status = "running"` is
    # what ``user_sync_running()`` reads and what the manual refresh endpoint
    # refuses a second run on, so any path that leaves it set jams the feature
    # for the life of the process — no later sync can clear it. That is what
    # used to happen when the client build raised (no stored secret, or MSAL's
    # tenant discovery rejecting the authority) outside the try below.
    try:
        now = now or datetime.now(timezone.utc)
        _user_sync.status = "running"
        _user_sync.detail = "Reading licensed users…"
        # Zeroed at the start: a failure must report nothing rather than the
        # counts the last successful run happened to leave behind.
        _user_sync.licensed_users = 0
        _user_sync.directory_users = 0
        _user_sync.updated_at = now.isoformat()

        async with session_factory() as session:
            if config is None:
                config = await load_app_config(session)
                if config is None or not config.tenant_id:
                    raise IngestError("Graph is not configured yet.")
            if graph is None:
                graph = build_graph_client(config)
                owns_graph = True

            job = JobRun(job_name="users", status="running")
            session.add(job)
            await session.flush()
            stats: dict[str, Any] = {}
            try:
                stats["licensed_users"] = await sync_licensed_users(
                    session, graph, config
                )
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
            except BaseException as exc:  # noqa: BLE001 - persisted for observability
                # BaseException, not Exception: a cancelled refresh (uvicorn
                # shutting down mid-run) must not leave the job row claiming to
                # be running, which is what Scan history and "last run" read.
                detail = str(exc) or "The user extraction stopped before it finished."
                # Release the flag before touching the database: if persisting
                # the failed job row then fails, the feature must still work.
                _mark_user_sync_failed(detail)
                stats["error"] = detail
                job.status = "failed"
                job.finished_at = datetime.now(timezone.utc)
                job.stats = stats
                try:
                    await session.commit()
                except BaseException:  # noqa: BLE001
                    # Under cancellation the commit is itself cancelled, so the
                    # row can still be left behind — the same gap run_ingest has.
                    logger.warning(
                        "Could not record the failed users job run", exc_info=True
                    )
                logger.exception("User sync failed")
                raise
            finally:
                if owns_graph and graph is not None:
                    await graph.aclose()
    except Exception as exc:
        # Raised before there was a job row to record it against — no credentials
        # stored, or the Graph client refusing to build.
        _mark_user_sync_failed(str(exc))
        raise
    finally:
        # CancelledError is a BaseException, so the handlers above never see a
        # cancelled refresh. Whatever path was taken, the flag does not survive;
        # a no-op once a real reason has already been recorded.
        _mark_user_sync_failed("The user extraction stopped before it finished.")


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
        "copilot_skus": [],
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
        skus = await graph.get_subscribed_skus()
        result["subscribed_skus"] = True
        granting = copilot_granting_skus(
            skus, override=list(config.copilot_sku_ids or [])
        )
        # Report every subscription with whether it counts, so an administrator
        # can see a SKU was considered and rejected rather than overlooked.
        result["copilot_skus"] = describe_granting_skus(skus, granting)
        count = 0
        async for user in graph.iter_licensed_users(sorted(granting)):
            if has_copilot_license(user, granting):
                count += 1
        result["copilot_licensed_users"] = count
        result["directory_read"] = True
        result["ok"] = True
    except Exception as exc:  # noqa: BLE001 - reported to caller
        result["detail"] = str(exc)
    finally:
        await graph.aclose()
    return result
