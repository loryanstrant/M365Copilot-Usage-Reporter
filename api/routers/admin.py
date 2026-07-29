"""Admin routes (admin role required).

Configure Graph credentials (secret encrypted, write-only), test the
connection, trigger an ingest run, and read run status. All routes here are
gated by :func:`api.auth.require_admin`.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import CurrentUser, require_admin
from api.schemas import (
    AppConfigIn,
    AppConfigOut,
    IngestRunOut,
    JobRunOut,
    StatusOut,
    TestConnectionOut,
)
from shared.crypto import encrypt
from shared.db import SessionLocal, get_session
from shared.models import AppConfig, EntraUser, JobRun, LicensedUser, Prompt
from worker.backfill import (
    get_progress,
    is_running as backfill_running,
    request_cancel,
    run_backfill,
)
from worker.ingest import run_ingest, test_graph_connection

logger = logging.getLogger("api.admin")

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

_DEFAULT_SKUS = ["639dec6b-bb19-468b-871c-c5c441c4b0cb"]
_ingest_lock = asyncio.Lock()


def _to_out(cfg: AppConfig | None) -> AppConfigOut:
    if cfg is None:
        return AppConfigOut(copilot_sku_ids=_DEFAULT_SKUS)
    return AppConfigOut(
        tenant_id=cfg.tenant_id,
        client_id=cfg.client_id,
        has_client_secret=bool(cfg.client_secret_encrypted),
        copilot_sku_ids=list(cfg.copilot_sku_ids or []),
        report_access_group_id=cfg.report_access_group_id,
        backfill_days=cfg.backfill_days,
        schedule_cron=cfg.schedule_cron,
        configured=bool(
            cfg.tenant_id and cfg.client_id and cfg.client_secret_encrypted
        ),
        updated_at=cfg.updated_at,
        updated_by=cfg.updated_by,
    )


async def _get_config(session: AsyncSession) -> AppConfig | None:
    return await session.get(AppConfig, 1)


@router.get("/config", response_model=AppConfigOut)
async def get_config(session: AsyncSession = Depends(get_session)) -> AppConfigOut:
    return _to_out(await _get_config(session))


@router.put("/config", response_model=AppConfigOut)
async def put_config(
    body: AppConfigIn,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AppConfigOut:
    cfg = await _get_config(session)
    if cfg is None:
        cfg = AppConfig(id=1, copilot_sku_ids=_DEFAULT_SKUS)
        session.add(cfg)

    if body.tenant_id is not None:
        cfg.tenant_id = body.tenant_id.strip() or None
    if body.client_id is not None:
        cfg.client_id = body.client_id.strip() or None
    # Client secret is write-only: only update when a value is supplied.
    if body.client_secret:
        cfg.client_secret_encrypted = encrypt(body.client_secret)
    if body.copilot_sku_ids is not None:
        cfg.copilot_sku_ids = [s.strip() for s in body.copilot_sku_ids if s.strip()]
    if body.report_access_group_id is not None:
        cfg.report_access_group_id = body.report_access_group_id.strip() or None
    if body.backfill_days is not None:
        cfg.backfill_days = body.backfill_days
    if body.schedule_cron is not None:
        cfg.schedule_cron = body.schedule_cron.strip() or None
    cfg.updated_by = user.username

    await session.commit()
    await session.refresh(cfg)
    return _to_out(cfg)


@router.post("/test-connection", response_model=TestConnectionOut)
async def test_connection(
    session: AsyncSession = Depends(get_session),
) -> TestConnectionOut:
    cfg = await _get_config(session)
    if cfg is None:
        return TestConnectionOut(ok=False, detail="Graph is not configured yet.")
    result = await test_graph_connection(cfg)
    return TestConnectionOut(**result)


async def _run_manual_ingest() -> None:
    async with _ingest_lock:
        try:
            await run_ingest(SessionLocal, job_name="manual")
        except Exception:  # pragma: no cover - logged for observability
            logger.exception("Manual ingest failed")


@router.post("/ingest/run", response_model=IngestRunOut)
async def ingest_run(background: BackgroundTasks) -> IngestRunOut:
    if _ingest_lock.locked():
        return IngestRunOut(
            status="already_running", detail="An ingest is already in progress."
        )
    background.add_task(_run_manual_ingest)
    return IngestRunOut(status="started", detail="Ingest started in the background.")


async def _run_backfill(lookback_days: int | None) -> None:
    try:
        await run_backfill(SessionLocal, lookback_days=lookback_days)
    except Exception:  # pragma: no cover - logged for observability
        logger.exception("Backfill failed")


@router.post("/backfill/run", response_model=IngestRunOut)
async def backfill_run(
    background: BackgroundTasks, lookback_days: int | None = None
) -> IngestRunOut:
    if backfill_running():
        return IngestRunOut(
            status="already_running", detail="A backfill is already in progress."
        )
    background.add_task(_run_backfill, lookback_days)
    return IngestRunOut(status="started", detail="Backfill started in the background.")


@router.get("/backfill/progress")
async def backfill_progress() -> dict:
    return get_progress()


@router.post("/backfill/cancel", response_model=IngestRunOut)
async def backfill_cancel() -> IngestRunOut:
    request_cancel()
    return IngestRunOut(status="cancelling", detail="Backfill cancellation requested.")


@router.get("/status", response_model=StatusOut)
async def status(session: AsyncSession = Depends(get_session)) -> StatusOut:
    cfg = await _get_config(session)
    last = await session.scalar(
        select(JobRun).order_by(JobRun.started_at.desc()).limit(1)
    )
    prompts = await session.scalar(select(func.count()).select_from(Prompt)) or 0
    conversations = (
        await session.scalar(
            select(func.count(func.distinct(Prompt.conversation_id)))
        )
        or 0
    )
    licensed = await session.scalar(select(func.count()).select_from(LicensedUser)) or 0
    entra = await session.scalar(select(func.count()).select_from(EntraUser)) or 0

    last_out = (
        JobRunOut(
            id=last.id,
            job_name=last.job_name,
            status=last.status,
            started_at=last.started_at,
            finished_at=last.finished_at,
            stats=last.stats,
        )
        if last is not None
        else None
    )
    return StatusOut(
        configured=bool(
            cfg and cfg.tenant_id and cfg.client_id and cfg.client_secret_encrypted
        ),
        last_run=last_out,
        prompts=prompts,
        conversations=conversations,
        licensed_users=licensed,
        entra_users=entra,
    )
