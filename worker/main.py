"""Worker entrypoint.

Runs the incremental ingestion engine on a fixed interval read from
``app_config.schedule_interval_hours`` (1..24; 24 = daily). A lightweight
supervisor re-reads the config every few minutes so a schedule change made in
the admin UI takes effect without restarting the container. If Graph is not
configured yet, scheduled runs log and skip until the admin saves credentials.
"""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from shared.config import settings
from shared.db import SessionLocal
from shared.models import AppConfig
from worker.ingest import IngestError, run_ingest

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("worker")

_DEFAULT_INTERVAL_HOURS = 24
_SUPERVISOR_MINUTES = 5


def clamp_interval_hours(hours: int | None) -> int:
    """Clamp the configured interval to 1..24 hours (never less than hourly,
    never more than once a day)."""
    if not hours or hours < 1:
        return _DEFAULT_INTERVAL_HOURS
    return min(hours, 24)


async def load_interval_hours() -> int:
    async with SessionLocal() as session:
        cfg = await session.scalar(select(AppConfig).limit(1))
        return clamp_interval_hours(cfg.schedule_interval_hours if cfg else None)


async def scheduled_ingest() -> None:
    try:
        stats = await run_ingest(SessionLocal, job_name="scheduled")
        logger.info("Scheduled ingest complete: %s", stats)
    except IngestError as exc:
        logger.info("Skipping scheduled ingest: %s", exc)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Scheduled ingest failed")


async def main() -> None:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.start()
    current: dict[str, int | None] = {"hours": None}

    async def apply_schedule() -> None:
        hours = await load_interval_hours()
        if hours != current["hours"]:
            current["hours"] = hours
            scheduler.add_job(
                scheduled_ingest,
                IntervalTrigger(hours=hours),
                id="ingest",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            logger.info("Ingest scheduled every %s hour(s).", hours)

    await apply_schedule()
    # Supervisor: re-check the configured interval periodically so UI changes
    # are picked up without a container restart.
    scheduler.add_job(
        apply_schedule,
        IntervalTrigger(minutes=_SUPERVISOR_MINUTES),
        id="schedule-supervisor",
        max_instances=1,
        coalesce=True,
    )

    logger.info("Worker started (env=%s).", settings.app_env)
    stop = asyncio.Event()
    try:
        await stop.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):  # pragma: no cover
        logger.info("Worker shutting down")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
