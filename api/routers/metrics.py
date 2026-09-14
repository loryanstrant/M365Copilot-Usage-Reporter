"""Metrics routes.

Exposes the SQL-based measures for the dashboard, split by who may see what:

``router`` — organisation-wide data. Gated by :func:`require_org_view`, so it
needs both a valid token and membership of the configured organisation-view
group (admins always pass).

``common_router`` — data any signed-in user may see regardless of that group:
slicer options, data freshness and build info.

``me_router`` — the personal view. Every route derives the person from the
token, never from a client-supplied id, so one user cannot read another's data
by editing a URL.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api import metrics
from api.auth import CurrentUser, get_current_user, require_org_view
from api.filters import MetricFilters
from shared.db import get_session

router = APIRouter(
    prefix="/metrics",
    tags=["metrics"],
    dependencies=[Depends(require_org_view)],
)

common_router = APIRouter(
    prefix="/metrics",
    tags=["metrics"],
    dependencies=[Depends(get_current_user)],
)

me_router = APIRouter(
    prefix="/metrics/me",
    tags=["metrics", "personal"],
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


@common_router.get("/filters")
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


@router.get("/by-app-daily")
async def get_by_app_daily(
    filters: MetricFilters = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.by_app_daily(session, filters=filters)


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
    filters: MetricFilters = Depends(get_filters),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.laggards(session, filters=filters, limit=limit)


@router.get("/coaching-pairs")
async def get_coaching_pairs(
    group_by: str = Query(default="department"),
    metric: str = Query(default="prompts"),
    per_group: int = Query(default=3, ge=1, le=10),
    filters: MetricFilters = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.coaching_pairs(
        session,
        filters=filters,
        group_by=group_by,
        metric=metric,
        per_group=per_group,
    )


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


@router.get("/breakdown")
async def get_breakdown(
    dim1: str = Query(default="app_name"),
    dim2: str = Query(default="chat_type"),
    filters: MetricFilters = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    allowed = {"app_name", "chat_type", "conversation_location", "department", "office_location"}
    if dim1 not in allowed or dim2 not in allowed:
        return []
    return await metrics.breakdown(session, dim1=dim1, dim2=dim2, filters=filters)


@router.get("/categories")
async def get_categories(session: AsyncSession = Depends(get_session)):
    return await metrics.categories(session)


@router.get("/active-inactive")
async def get_active_inactive(session: AsyncSession = Depends(get_session)):
    return await metrics.active_inactive(session)


@router.get("/briefing")
async def get_briefing(session: AsyncSession = Depends(get_session)):
    return await metrics.briefing(session)


@router.get("/licenses")
async def get_licenses(session: AsyncSession = Depends(get_session)):
    return await metrics.licenses(session)


@common_router.get("/freshness")
async def get_freshness(session: AsyncSession = Depends(get_session)):
    return await metrics.freshness(session)


@common_router.get("/about")
async def get_about() -> dict:
    """Version and build metadata for the About page."""
    from shared.version import APP_VERSION, BUILD_DATE, BUILD_TIME

    return {
        "version": APP_VERSION,
        "build_date": BUILD_DATE,
        "build_time": BUILD_TIME,
    }


# --------------------------------------------------------------------------- #
# Personal view
#
# Every route here scopes to the signed-in person using the object ID carried in
# their token. There is deliberately no "which user?" parameter: if the caller
# could name the user, any viewer could read anyone's activity by editing a URL.
# --------------------------------------------------------------------------- #
def _me_filters(user: CurrentUser, base: MetricFilters) -> MetricFilters:
    """Narrow the shared slicers down to just this person."""
    if not user.oid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "There is no personal view for this account. Sign in with your "
                "work account to see your own activity."
            ),
        )
    base.user_ids = [user.oid]
    return base


@me_router.get("/summary")
async def get_my_summary(
    user: CurrentUser = Depends(get_current_user),
    filters: MetricFilters = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.summary(session, filters=_me_filters(user, filters))


@me_router.get("/daily")
async def get_my_daily(
    user: CurrentUser = Depends(get_current_user),
    filters: MetricFilters = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.daily(session, filters=_me_filters(user, filters))


@me_router.get("/by-app")
async def get_my_by_app(
    user: CurrentUser = Depends(get_current_user),
    filters: MetricFilters = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.by_app(session, filters=_me_filters(user, filters))


@me_router.get("/copilot-score")
async def get_my_copilot_score(
    user: CurrentUser = Depends(get_current_user),
    filters: MetricFilters = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    return await metrics.copilot_score(session, filters=_me_filters(user, filters))


@me_router.get("/comparison")
async def get_my_comparison(
    user: CurrentUser = Depends(get_current_user),
    filters: MetricFilters = Depends(get_filters),
    session: AsyncSession = Depends(get_session),
):
    """This person's prompt count against the organisation median.

    Only the aggregate is returned — never another individual's figures — so
    this stays safe to show to someone without organisation-wide access.
    """
    from copy import deepcopy

    org_filters = deepcopy(filters)
    org_filters.user_ids = []

    mine = await metrics.summary(session, filters=_me_filters(user, deepcopy(filters)))
    rows = await metrics.by_user(session, filters=org_filters)

    counts = sorted(
        int(r.get("prompts") or 0) for r in rows if (r.get("prompts") or 0) > 0
    )
    median = 0
    if counts:
        mid = len(counts) // 2
        median = (
            counts[mid]
            if len(counts) % 2
            else (counts[mid - 1] + counts[mid]) // 2
        )

    my_prompts = int(mine.get("prompts") or 0)
    return {
        "my_prompts": my_prompts,
        "org_median_prompts": median,
        "people_counted": len(counts),
        "above_median": my_prompts >= median,
    }
