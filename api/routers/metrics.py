"""Metrics routes (any authenticated user).

Exposes the SQL-based measures for the dashboard. All routes require a valid
token but not the admin role, so viewers can see reports. Every report route
accepts the shared slicer query params via the ``filters`` dependency.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api import metrics
from api.auth import get_current_user
from api.filters import MetricFilters
from shared.db import get_session

router = APIRouter(
    prefix="/metrics",
    tags=["metrics"],
    dependencies=[Depends(get_current_user)],
)


def get_filters(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    app: list[str] | None = Query(default=None),
    department: list[str] | None = Query(default=None),
    manager_id: list[str] | None = Query(default=None),
    office_location: list[str] | None = Query(default=None),
    company: list[str] | None = Query(default=None),
    job_title: list[str] | None = Query(default=None),
    user_search: str | None = Query(default=None),
    chat_type: list[str] | None = Query(default=None),
    conversation_location: list[str] | None = Query(default=None),
) -> MetricFilters:
    return MetricFilters(
        date_from=date_from,
        date_to=date_to,
        apps=app or [],
        departments=department or [],
        manager_ids=manager_id or [],
        offices=office_location or [],
        companies=company or [],
        job_titles=job_title or [],
        chat_types=chat_type or [],
        conversation_locations=conversation_location or [],
        user_search=user_search,
    )


@router.get("/filters")
async def get_filter_options(session: AsyncSession = Depends(get_session)):
    return await metrics.filter_options(session)


@router.get("/summary")
async def get_summary(
    filters: MetricFilters = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.summary(session, filters=filters)


@router.get("/copilot-score")
async def get_copilot_score(
    filters: MetricFilters = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.copilot_score(session, filters=filters)


@router.get("/daily")
async def get_daily(
    filters: MetricFilters = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.daily(session, filters=filters)


@router.get("/by-app")
async def get_by_app(
    filters: MetricFilters = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.by_app(session, filters=filters)


@router.get("/by-user")
async def get_by_user(
    filters: MetricFilters = Depends(get_filters),
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.by_user(session, filters=filters, limit=limit)


@router.get("/leaderboard-rollups")
async def get_leaderboard_rollups(
    filters: MetricFilters = Depends(get_filters),
    limit: int = Query(default=5, ge=1, le=25),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.leaderboard_rollups(session, filters=filters, limit=limit)


@router.get("/laggards")
async def get_laggards(
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.laggards(session, limit=limit)


@router.get("/locations")
async def get_locations(
    filters: MetricFilters = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.locations(session, filters=filters)


@router.get("/chat-types")
async def get_chat_types(
    filters: MetricFilters = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.chat_types(session, filters=filters)


@router.get("/categories")
async def get_categories(session: AsyncSession = Depends(get_session)):
    return await metrics.categories(session)


@router.get("/active-inactive")
async def get_active_inactive(session: AsyncSession = Depends(get_session)):
    return await metrics.active_inactive(session)


@router.get("/licenses")
async def get_licenses(session: AsyncSession = Depends(get_session)):
    return await metrics.licenses(session)


@router.get("/freshness")
async def get_freshness(session: AsyncSession = Depends(get_session)):
    return await metrics.freshness(session)
