"""FastAPI application entrypoint.

Exposes a ``/health`` endpoint that verifies database connectivity and, in
production, serves the built frontend bundle. Feature routers are mounted in
later phases.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from shared.config import settings
from shared.db import engine

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("api")


async def _seed_admin_from_env() -> None:
    """Create a first admin from ADMIN_USERNAME/ADMIN_PASSWORD when no users exist."""
    if not (settings.admin_username and settings.admin_password):
        return
    from sqlalchemy import func, select

    from shared.db import SessionLocal
    from shared.models import AppUser
    from shared.security import hash_password

    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(AppUser))
        if count:
            return
        session.add(
            AppUser(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                role="admin",
            )
        )
        await session.commit()
        logger.info("Seeded initial admin user '%s'.", settings.admin_username)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Run database migrations to head before serving traffic."""
    if os.getenv("RUN_MIGRATIONS_ON_STARTUP", "true").lower() != "false":
        try:
            from shared.migrate import upgrade_to_head

            upgrade_to_head()
        except Exception as exc:  # pragma: no cover - startup diagnostics
            logger.error("Migration on startup failed: %s", exc)
    try:
        await _seed_admin_from_env()
    except Exception as exc:  # pragma: no cover - startup diagnostics
        logger.error("Admin seeding failed: %s", exc)
    yield


app = FastAPI(
    title="M365 Copilot Usage Reporter",
    version="0.1.0",
    description="Ingests Microsoft 365 Copilot usage and serves a usage dashboard.",
    lifespan=lifespan,
)


@app.get("/health", tags=["system"])
async def health() -> JSONResponse:
    """Liveness/readiness probe: returns 200 only when the database is reachable."""
    db_ok = False
    detail = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # pragma: no cover - exercised via integration
        detail = f"database unavailable: {exc}"
        logger.warning("Health check failed: %s", detail)

    status_code = 200 if db_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if db_ok else "degraded",
            "database": db_ok,
            "environment": settings.app_env,
            "detail": detail,
        },
    )


def _register_routers() -> None:
    """Mount feature routers (kept in a function so imports stay lazy-free)."""
    from api.routers import admin, auth, metrics

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(metrics.router)


_register_routers()


def _mount_frontend() -> None:
    """Serve the built SPA bundle when it exists (production single-container).

    Static assets are served directly; any other GET path falls back to
    ``index.html`` so the client-side router handles deep links (e.g. /settings).
    API routes registered above always take precedence.
    """
    dist = settings.frontend_dist
    index_path = os.path.join(dist, "index.html")
    if not os.path.isfile(index_path):
        logger.info("Frontend bundle not found at %s (dev mode)", dist)
        return

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    assets_dir = os.path.join(dist, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        candidate = os.path.join(dist, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(index_path)

    logger.info("Serving frontend bundle from %s", dist)


_mount_frontend()
