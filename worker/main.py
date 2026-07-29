"""Worker entrypoint.

Runs the ingestion engine on a cron schedule via APScheduler. If Graph is not
configured yet (no ``app_config`` row), scheduled runs log and skip until the
admin saves credentials in the UI.
"""
from __future__ import annotations

import asyncio
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from shared.config import settings
from shared.db import SessionLocal
from worker.ingest import IngestError, run_ingest

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("worker")

# Default: daily at 02:00. Override with INGEST_CRON (5-field crontab).
_DEFAULT_CRON = "0 2 * * *"


async def scheduled_ingest() -> None:
    try:
        stats = await run_ingest(SessionLocal, job_name="scheduled")
        logger.info("Scheduled ingest complete: %s", stats)
    except IngestError as exc:
        logger.info("Skipping scheduled ingest: %s", exc)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Scheduled ingest failed")


async def main() -> None:
    cron = os.getenv("INGEST_CRON", _DEFAULT_CRON)
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        scheduled_ingest,
        CronTrigger.from_crontab(cron, timezone="UTC"),
        id="ingest",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "Worker started (env=%s); ingest scheduled with cron '%s' (UTC).",
        settings.app_env,
        cron,
    )
    stop = asyncio.Event()
    try:
        await stop.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):  # pragma: no cover
        logger.info("Worker shutting down")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
