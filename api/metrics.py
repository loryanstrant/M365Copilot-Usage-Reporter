"""Metrics queries — the DAX measures re-expressed as deterministic SQL.

All output uses the project vocabulary: **Prompts** (rows) and **Conversations**
(distinct ``conversation_id``); never "interactions"/"sessions". Functions take
an explicit ``today`` so results are deterministic under test, and a
``MetricFilters`` so every page can slice by date, app, department, manager,
office, company, job title, user, chat type and conversation location.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import Select, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.filters import MetricFilters
from shared.models import EntraUser, JobRun, LicenseCount, LicensedUser, Prompt

_ACTIVE_WINDOW_DAYS = 30

# CopilotScore tiers (from the original DAX SWITCH ladder). Configurable later.
_SCORE_LADDER: list[tuple[int, int]] = [
    (10000, 100), (9000, 90), (8000, 80), (7000, 70), (6000, 60),
    (5000, 50), (4500, 45), (4000, 40), (3500, 35), (3000, 30), (2500, 25),
] + [(t, t // 100) for t in range(2000, 0, -100)]


def _avg(prompts: int, conversations: int) -> float:
    return round(prompts / conversations, 2) if conversations else 0.0


def _days_since(value: date | None, today: date) -> int | None:
    return (today - value).days if value is not None else None


def _conv_key():
    """Conversation identity for distinct-counting.

    A conversation is the Graph ``sessionId``. When a genuine human prompt has no
    session (e.g. a one-shot Copilot action in Word/Excel), ``sessionId`` is NULL —
    and ``COUNT(DISTINCT sessionId)`` silently *drops* those rows, so a day of 500
    session-less prompts could collapse to a handful of conversations and produce
    impossible prompt:conversation ratios. Falling back to the prompt's own id
    counts each session-less prompt as its own conversation (a no-op whenever a
    real session id is present)."""
    return func.coalesce(Prompt.conversation_id, Prompt.prompt_id)


def copilot_score_from_count(prompt_count: int) -> int:
    for threshold, score in _SCORE_LADDER:
        if prompt_count >= threshold:
            return score
    return 0


def _prompt_query(
    f: MetricFilters, *cols: Any, join_user: bool = False
) -> Select:
    """``select(cols)`` over prompts, joining ``entra_users`` when a directory
    dimension is filtered or ``join_user`` is requested (e.g. grouping by dept)."""
    q = select(*cols).select_from(Prompt)
    if f.needs_user_join or join_user:
        q = q.join(EntraUser, EntraUser.user_id == Prompt.user_id)
    return q.where(*f.all_conds())


async def summary(
    session: AsyncSession,
    *,
    filters: MetricFilters | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Overview KPIs: prompts, conversations, avg, active users, adoption, licenses."""
    f = filters or MetricFilters()
    today = today or date.today()
    window_start = today - timedelta(days=_ACTIVE_WINDOW_DAYS)

    prompts = (await session.scalar(_prompt_query(f, func.count()))) or 0
    conversations = (
        await session.scalar(
            _prompt_query(f, func.count(distinct(_conv_key())))
        )
    ) or 0
    active_users = (
        await session.scalar(
            select(func.count(distinct(Prompt.user_id))).where(
                Prompt.prompt_date >= window_start
            )
        )
    ) or 0
    licensed_users = (
        await session.scalar(select(func.count()).select_from(LicensedUser))
    ) or 0
    directory_users = (
        await session.scalar(select(func.count()).select_from(EntraUser))
    ) or 0

    enabled = allocated = available = 0
    latest_date = await session.scalar(select(func.max(LicenseCount.recorded_date)))
    if latest_date is not None:
        row = (
            await session.execute(
                select(
                    func.sum(LicenseCount.enabled),
                    func.sum(LicenseCount.allocated),
                    func.sum(LicenseCount.available),
                ).where(LicenseCount.recorded_date == latest_date)
            )
        ).one()
        enabled, allocated, available = (int(x or 0) for x in row)

    return {
        "prompts": prompts,
        "conversations": conversations,
        "avg_prompts_per_conversation": _avg(prompts, conversations),
        "active_users": active_users,
        "licensed_users": licensed_users,
        "directory_users": directory_users,
        "adoption_rate": round(active_users / licensed_users, 4)
        if licensed_users
        else 0.0,
        "copilot_score": copilot_score_from_count(prompts),
        "license_enabled": enabled,
        "license_allocated": allocated,
        "license_available": available,
    }


async def copilot_score(
    session: AsyncSession, *, filters: MetricFilters | None = None
) -> dict[str, Any]:
    f = filters or MetricFilters()
    prompts = (await session.scalar(_prompt_query(f, func.count()))) or 0
    return {"prompts": prompts, "score": copilot_score_from_count(prompts)}


async def daily(
    session: AsyncSession, *, filters: MetricFilters | None = None
) -> list[dict[str, Any]]:
    """Prompts and conversations per day (for the trend line)."""
    f = filters or MetricFilters()
    q = (
        _prompt_query(
            f,
            Prompt.prompt_date.label("date"),
            func.count().label("prompts"),
            func.count(distinct(_conv_key())).label("conversations"),
        )
        .where(Prompt.prompt_date.is_not(None))
        .group_by(Prompt.prompt_date)
        .order_by(Prompt.prompt_date)
    )
    return [
        {
            "date": r.date.isoformat() if r.date else None,
            "prompts": r.prompts,
            "conversations": r.conversations,
        }
        for r in (await session.execute(q)).all()
    ]


async def by_app_daily(
    session: AsyncSession, *, filters: MetricFilters | None = None
) -> list[dict[str, Any]]:
    """Prompts and conversations per app per day (per-app trend small multiples)."""
    f = filters or MetricFilters()
    q = (
        _prompt_query(
            f,
            Prompt.app_name.label("app_name"),
            Prompt.prompt_date.label("date"),
            func.count().label("prompts"),
            func.count(distinct(_conv_key())).label("conversations"),
        )
        .where(Prompt.prompt_date.is_not(None), Prompt.app_name.is_not(None))
        .group_by(Prompt.app_name, Prompt.prompt_date)
        .order_by(Prompt.app_name, Prompt.prompt_date)
    )
    return [
        {
            "app_name": r.app_name,
            "date": r.date.isoformat() if r.date else None,
            "prompts": r.prompts,
            "conversations": r.conversations,
        }
        for r in (await session.execute(q)).all()
    ]


async def by_app(
    session: AsyncSession,
    *,
    filters: MetricFilters | None = None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Per-app usage with first/last use and days since last."""
    f = filters or MetricFilters()
    today = today or date.today()
    q = (
        _prompt_query(
            f,
            Prompt.app_name.label("app_name"),
            func.count().label("prompts"),
            func.count(distinct(_conv_key())).label("conversations"),
            func.count(distinct(Prompt.user_id)).label("users"),
            func.min(Prompt.prompt_date).label("first_use"),
            func.max(Prompt.prompt_date).label("last_use"),
        )
        .group_by(Prompt.app_name)
        .order_by(func.count().desc())
    )
    out: list[dict[str, Any]] = []
    for r in (await session.execute(q)).all():
        out.append(
            {
                "app_name": r.app_name,
                "prompts": r.prompts,
                "conversations": r.conversations,
                "avg_prompts_per_conversation": _avg(r.prompts, r.conversations),
                "users": r.users,
                "first_use": r.first_use.isoformat() if r.first_use else None,
                "last_use": r.last_use.isoformat() if r.last_use else None,
                "days_since_last": _days_since(r.last_use, today),
            }
        )
    return out


async def by_user(
    session: AsyncSession,
    *,
    filters: MetricFilters | None = None,
    limit: int = 100,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Per-user usage table (leaderboard-ordered), joined to directory info."""
    f = filters or MetricFilters()
    today = today or date.today()
    q = (
        select(
            Prompt.user_id.label("user_id"),
            EntraUser.display_name.label("display_name"),
            EntraUser.department.label("department"),
            EntraUser.office_location.label("office_location"),
            EntraUser.manager_id.label("manager_id"),
            EntraUser.has_copilot_license.label("has_copilot_license"),
            func.count().label("prompts"),
            func.count(distinct(_conv_key())).label("conversations"),
            func.min(Prompt.prompt_date).label("first_use"),
            func.max(Prompt.prompt_date).label("last_use"),
        )
        .select_from(Prompt)
        .join(EntraUser, EntraUser.user_id == Prompt.user_id, isouter=True)
        .where(*f.all_conds())
        .group_by(
            Prompt.user_id,
            EntraUser.display_name,
            EntraUser.department,
            EntraUser.office_location,
            EntraUser.manager_id,
            EntraUser.has_copilot_license,
        )
        .order_by(func.count().desc())
        .limit(limit)
    )
    out: list[dict[str, Any]] = []
    for r in (await session.execute(q)).all():
        out.append(
            {
                "user_id": r.user_id,
                "display_name": r.display_name,
                "department": r.department,
                "office_location": r.office_location,
                "manager_id": r.manager_id,
                "has_copilot_license": bool(r.has_copilot_license),
                "prompts": r.prompts,
                "conversations": r.conversations,
                "avg_prompts_per_conversation": _avg(r.prompts, r.conversations),
                "first_use": r.first_use.isoformat() if r.first_use else None,
                "last_use": r.last_use.isoformat() if r.last_use else None,
                "days_since_last": _days_since(r.last_use, today),
            }
        )
    return out


async def categories(
    session: AsyncSession, *, today: date | None = None
) -> list[dict[str, Any]]:
    """Trailing-30-day prompt-count buckets across licensed users."""
    today = today or date.today()
    window_start = today - timedelta(days=_ACTIVE_WINDOW_DAYS)

    counts = dict(
        (
            await session.execute(
                select(Prompt.user_id, func.count())
                .where(Prompt.prompt_date >= window_start)
                .group_by(Prompt.user_id)
            )
        ).all()
    )
    licensed_ids = [
        uid for (uid,) in (await session.execute(select(LicensedUser.user_id))).all()
    ]

    labels = ["0", "<10", "10-50", "50-100", ">100"]
    buckets = {label: 0 for label in labels}
    for uid in licensed_ids:
        c = int(counts.get(uid, 0))
        if c == 0:
            buckets["0"] += 1
        elif c < 10:
            buckets["<10"] += 1
        elif c <= 50:
            buckets["10-50"] += 1
        elif c <= 100:
            buckets["50-100"] += 1
        else:
            buckets[">100"] += 1
    return [{"category": label, "users": buckets[label]} for label in labels]


async def active_inactive(
    session: AsyncSession, *, today: date | None = None
) -> dict[str, int]:
    """Licensed users active (prompt in last 30 days) vs inactive."""
    today = today or date.today()
    window_start = today - timedelta(days=_ACTIVE_WINDOW_DAYS)
    licensed = (
        await session.scalar(select(func.count()).select_from(LicensedUser))
    ) or 0
    active = (
        await session.scalar(
            select(func.count(distinct(Prompt.user_id))).where(
                Prompt.prompt_date >= window_start,
                Prompt.user_id.in_(select(LicensedUser.user_id)),
            )
        )
    ) or 0
    return {"active": active, "inactive": max(licensed - active, 0), "licensed": licensed}


async def briefing(
    session: AsyncSession, *, today: date | None = None, window_days: int = 30
) -> dict[str, Any]:
    """Executive snapshot: the current ``window_days`` period vs the one before
    it, plus leading surfaces and departments. Feeds the narrated briefing page.
    """
    today = today or date.today()
    cur_start = today - timedelta(days=window_days)
    prev_start = today - timedelta(days=2 * window_days)

    async def _counts(lo: date, hi: date | None) -> dict[str, int]:
        conds: list[Any] = [Prompt.prompt_date >= lo]
        if hi is not None:
            conds.append(Prompt.prompt_date < hi)
        prompts = (await session.scalar(select(func.count()).where(*conds))) or 0
        conversations = (
            await session.scalar(
                select(func.count(distinct(_conv_key()))).where(*conds)
            )
        ) or 0
        active = (
            await session.scalar(
                select(func.count(distinct(Prompt.user_id))).where(*conds)
            )
        ) or 0
        return {
            "prompts": int(prompts),
            "conversations": int(conversations),
            "active_users": int(active),
        }

    current = await _counts(cur_start, None)
    previous = await _counts(prev_start, cur_start)

    licensed_users = (
        await session.scalar(select(func.count()).select_from(LicensedUser))
    ) or 0
    active_licensed = (
        await session.scalar(
            select(func.count(distinct(Prompt.user_id))).where(
                Prompt.prompt_date >= cur_start,
                Prompt.user_id.in_(select(LicensedUser.user_id)),
            )
        )
    ) or 0
    inactive_users = max(int(licensed_users) - int(active_licensed), 0)
    total_prompts = (
        await session.scalar(select(func.count()).select_from(Prompt))
    ) or 0

    cur_by_app = dict(
        (
            await session.execute(
                select(Prompt.app_name, func.count())
                .where(Prompt.prompt_date >= cur_start, Prompt.app_name.is_not(None))
                .group_by(Prompt.app_name)
            )
        ).all()
    )
    prev_by_app = dict(
        (
            await session.execute(
                select(Prompt.app_name, func.count())
                .where(
                    Prompt.prompt_date >= prev_start,
                    Prompt.prompt_date < cur_start,
                    Prompt.app_name.is_not(None),
                )
                .group_by(Prompt.app_name)
            )
        ).all()
    )
    top_apps = [
        {
            "name": name,
            "prompts": int(cnt),
            "prev_prompts": int(prev_by_app.get(name, 0)),
        }
        for name, cnt in sorted(
            cur_by_app.items(), key=lambda kv: kv[1], reverse=True
        )[:5]
    ]

    dept_rows = (
        await session.execute(
            select(EntraUser.department, func.count())
            .select_from(Prompt)
            .join(EntraUser, EntraUser.user_id == Prompt.user_id)
            .where(Prompt.prompt_date >= cur_start, EntraUser.department.is_not(None))
            .group_by(EntraUser.department)
            .order_by(func.count().desc())
            .limit(3)
        )
    ).all()
    top_departments = [{"name": d, "prompts": int(c)} for d, c in dept_rows]

    return {
        "window_days": window_days,
        "period_start": cur_start.isoformat(),
        "period_end": today.isoformat(),
        "previous_period_start": prev_start.isoformat(),
        "current": current,
        "previous": previous,
        "licensed_users": int(licensed_users),
        "active_users": current["active_users"],
        "adoption_rate": round(int(active_licensed) / int(licensed_users), 4)
        if licensed_users
        else 0.0,
        "inactive_users": inactive_users,
        "copilot_score": copilot_score_from_count(int(total_prompts)),
        "total_prompts": int(total_prompts),
        "top_apps": top_apps,
        "top_departments": top_departments,
    }


async def _grouped_counts(
    session: AsyncSession,
    column: Any,
    f: MetricFilters,
    *,
    limit: int | None = None,
    join_user: bool = False,
) -> list[dict[str, Any]]:
    """Prompt & conversation counts grouped by an arbitrary column."""
    q = (
        _prompt_query(
            f,
            column.label("name"),
            func.count().label("prompts"),
            func.count(distinct(_conv_key())).label("conversations"),
            join_user=join_user,
        )
        .where(column.is_not(None))
        .group_by(column)
        .order_by(func.count().desc())
    )
    if limit:
        q = q.limit(limit)
    return [
        {"name": r.name, "prompts": r.prompts, "conversations": r.conversations}
        for r in (await session.execute(q)).all()
    ]


async def locations(
    session: AsyncSession, *, filters: MetricFilters | None = None
) -> dict[str, Any]:
    """Where Copilot is used: chat types, Teams locations, file locations, and a
    per-day chat-type trend (for the streamgraph / stacked area)."""
    f = filters or MetricFilters()
    chat_type_split = await _grouped_counts(session, Prompt.chat_type, f)
    conversation_locations = await _grouped_counts(
        session, Prompt.conversation_location, f
    )
    teams_locations = await _grouped_counts(session, Prompt.teams_location, f, limit=15)
    file_locations = await _grouped_counts(session, Prompt.file_location, f, limit=15)

    trend_q = (
        _prompt_query(
            f,
            Prompt.prompt_date.label("date"),
            Prompt.chat_type.label("chat_type"),
            func.count().label("prompts"),
            func.count(distinct(_conv_key())).label("conversations"),
        )
        .where(Prompt.prompt_date.is_not(None))
        .group_by(Prompt.prompt_date, Prompt.chat_type)
        .order_by(Prompt.prompt_date)
    )
    trend = [
        {
            "date": r.date.isoformat() if r.date else None,
            "chat_type": r.chat_type or "Unknown",
            "prompts": r.prompts,
            "conversations": r.conversations,
        }
        for r in (await session.execute(trend_q)).all()
    ]
    return {
        "chat_types": chat_type_split,
        "conversation_locations": conversation_locations,
        "teams_locations": teams_locations,
        "file_locations": file_locations,
        "daily_by_chat_type": trend,
    }


async def chat_types(
    session: AsyncSession, *, filters: MetricFilters | None = None
) -> dict[str, Any]:
    """Chat-type (Work/Web/Temporary) and conversation-location (App/Chat) splits."""
    f = filters or MetricFilters()
    return {
        "chat_types": await _grouped_counts(session, Prompt.chat_type, f),
        "conversation_locations": await _grouped_counts(
            session, Prompt.conversation_location, f
        ),
    }


async def leaderboard_rollups(
    session: AsyncSession,
    *,
    filters: MetricFilters | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Top users / departments / offices / managers by prompt volume."""
    f = filters or MetricFilters()

    users = await by_user(session, filters=f, limit=limit)
    departments = await _grouped_counts(
        session, EntraUser.department, f, limit=limit, join_user=True
    )
    offices = await _grouped_counts(
        session, EntraUser.office_location, f, limit=limit, join_user=True
    )

    mgr = EntraUser.__table__.alias("mgr")
    q = (
        select(
            EntraUser.manager_id.label("manager_id"),
            mgr.c.display_name.label("manager_name"),
            func.count().label("prompts"),
            func.count(distinct(_conv_key())).label("conversations"),
        )
        .select_from(Prompt)
        .join(EntraUser, EntraUser.user_id == Prompt.user_id)
        .join(mgr, mgr.c.user_id == EntraUser.manager_id, isouter=True)
        .where(EntraUser.manager_id.is_not(None), *f.all_conds())
        .group_by(EntraUser.manager_id, mgr.c.display_name)
        .order_by(func.count().desc())
        .limit(limit)
    )
    managers = [
        {
            "name": r.manager_name or r.manager_id,
            "manager_id": r.manager_id,
            "prompts": r.prompts,
            "conversations": r.conversations,
        }
        for r in (await session.execute(q)).all()
    ]
    return {
        "users": users,
        "departments": departments,
        "offices": offices,
        "managers": managers,
    }


async def laggards(
    session: AsyncSession,
    *,
    today: date | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Licensed users with no/low recent usage, plus laggard rollups."""
    today = today or date.today()
    window_start = today - timedelta(days=_ACTIVE_WINDOW_DAYS)

    recent = dict(
        (
            await session.execute(
                select(Prompt.user_id, func.count())
                .where(Prompt.prompt_date >= window_start)
                .group_by(Prompt.user_id)
            )
        ).all()
    )
    last_use = dict(
        (
            await session.execute(
                select(Prompt.user_id, func.max(Prompt.prompt_date)).group_by(
                    Prompt.user_id
                )
            )
        ).all()
    )
    licensed_ids = [
        uid for (uid,) in (await session.execute(select(LicensedUser.user_id))).all()
    ]
    users_by_id = {
        u.user_id: u
        for u in (
            await session.execute(
                select(EntraUser).where(EntraUser.user_id.in_(licensed_ids))
            )
        ).scalars()
    }

    rows: list[dict[str, Any]] = []
    dept_idle: dict[str, int] = {}
    office_idle: dict[str, int] = {}
    for uid in licensed_ids:
        recent_count = int(recent.get(uid, 0))
        lu = last_use.get(uid)
        u = users_by_id.get(uid)
        inactive = recent_count == 0
        rows.append(
            {
                "user_id": uid,
                "display_name": (u.display_name if u else None) or uid,
                "department": u.department if u else None,
                "office_location": u.office_location if u else None,
                "prompts_30d": recent_count,
                "last_use": lu.isoformat() if lu else None,
                "days_since_last": _days_since(lu, today),
                "inactive": inactive,
            }
        )
        if inactive and u is not None:
            if u.department:
                dept_idle[u.department] = dept_idle.get(u.department, 0) + 1
            if u.office_location:
                office_idle[u.office_location] = office_idle.get(u.office_location, 0) + 1

    rows.sort(
        key=lambda r: (r["days_since_last"] is not None, r["days_since_last"] or 0),
        reverse=True,
    )

    def _top(d: dict[str, int]) -> list[dict[str, Any]]:
        return [
            {"name": k, "inactive_users": v}
            for k, v in sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:5]
        ]

    return {
        "users": rows[:limit],
        "top_departments": _top(dept_idle),
        "top_offices": _top(office_idle),
    }


async def filter_options(session: AsyncSession) -> dict[str, Any]:
    """Distinct values for every slicer (populates the UI dropdowns)."""

    async def _distinct(column: Any) -> list[str]:
        rows = (
            await session.execute(
                select(distinct(column)).where(column.is_not(None)).order_by(column)
            )
        ).all()
        return [r[0] for r in rows if r[0] not in (None, "")]

    managers_q = select(distinct(EntraUser.manager_id)).where(
        EntraUser.manager_id.is_not(None)
    )
    manager_ids = [r[0] for r in (await session.execute(managers_q)).all() if r[0]]
    mgr_names = {
        u.user_id: u.display_name
        for u in (
            await session.execute(
                select(EntraUser).where(EntraUser.user_id.in_(manager_ids))
            )
        ).scalars()
    }
    managers = sorted(
        ({"id": mid, "name": mgr_names.get(mid) or mid} for mid in manager_ids),
        key=lambda m: m["name"],
    )

    return {
        "apps": await _distinct(Prompt.app_name),
        "departments": await _distinct(EntraUser.department),
        "offices": await _distinct(EntraUser.office_location),
        "companies": await _distinct(EntraUser.company_name),
        "job_titles": await _distinct(EntraUser.job_title),
        "chat_types": await _distinct(Prompt.chat_type),
        "conversation_locations": await _distinct(Prompt.conversation_location),
        "managers": managers,
    }


async def breakdown(
    session: AsyncSession,
    *,
    dim1: str,
    dim2: str,
    filters: MetricFilters | None = None,
    limit1: int = 8,
    limit2: int = 8,
) -> list[dict[str, Any]]:
    """Prompt & conversation counts grouped by two dimensions (sunburst / radar).

    ``dim1``/``dim2`` are one of: app_name, chat_type, conversation_location
    (from prompts) or department, office_location (from entra_users). Returns
    rows ``{d1, d2, prompts, conversations}`` limited to the top ``limit1`` d1
    values (ranked by prompt volume).
    """
    cols = {
        "app_name": Prompt.app_name,
        "chat_type": Prompt.chat_type,
        "conversation_location": Prompt.conversation_location,
        "department": EntraUser.department,
        "office_location": EntraUser.office_location,
    }
    c1, c2 = cols[dim1], cols[dim2]
    f = filters or MetricFilters()
    join_user = dim1 in ("department", "office_location") or dim2 in (
        "department",
        "office_location",
    )
    q = (
        _prompt_query(
            f,
            c1.label("d1"),
            c2.label("d2"),
            func.count().label("prompts"),
            func.count(distinct(_conv_key())).label("conversations"),
            join_user=join_user,
        )
        .where(c1.is_not(None), c2.is_not(None))
        .group_by(c1, c2)
        .order_by(func.count().desc())
    )
    rows = [
        {"d1": r.d1, "d2": r.d2, "prompts": r.prompts, "conversations": r.conversations}
        for r in (await session.execute(q)).all()
    ]
    # Keep only the top d1 values so the visual stays readable.
    top1 = [
        name
        for name, _ in sorted(
            _sum_by(rows, "d1").items(), key=lambda kv: kv[1], reverse=True
        )[:limit1]
    ]
    top2 = [
        name
        for name, _ in sorted(
            _sum_by(rows, "d2").items(), key=lambda kv: kv[1], reverse=True
        )[:limit2]
    ]
    return [r for r in rows if r["d1"] in top1 and r["d2"] in top2]


def _sum_by(rows: list[dict[str, Any]], key: str) -> dict[Any, int]:
    out: dict[Any, int] = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + r["prompts"]
    return out


async def licenses(session: AsyncSession) -> list[dict[str, Any]]:
    """License totals over time (enabled / allocated / available)."""
    q = (
        select(
            LicenseCount.recorded_date.label("date"),
            func.sum(LicenseCount.enabled).label("enabled"),
            func.sum(LicenseCount.allocated).label("allocated"),
            func.sum(LicenseCount.available).label("available"),
        )
        .group_by(LicenseCount.recorded_date)
        .order_by(LicenseCount.recorded_date)
    )
    return [
        {
            "date": r.date.isoformat() if r.date else None,
            "enabled": int(r.enabled or 0),
            "allocated": int(r.allocated or 0),
            "available": int(r.available or 0),
        }
        for r in (await session.execute(q)).all()
    ]


async def freshness(session: AsyncSession) -> dict[str, Any]:
    """Data-freshness summary for the About page (viewer-accessible)."""
    last = await session.scalar(
        select(JobRun).order_by(JobRun.started_at.desc()).limit(1)
    )
    prompts = (await session.scalar(select(func.count()).select_from(Prompt))) or 0
    conversations = (
        await session.scalar(select(func.count(distinct(_conv_key()))))
    ) or 0
    licensed = (
        await session.scalar(select(func.count()).select_from(LicensedUser))
    ) or 0
    directory = (
        await session.scalar(select(func.count()).select_from(EntraUser))
    ) or 0
    span = (
        await session.execute(
            select(func.min(Prompt.prompt_date), func.max(Prompt.prompt_date))
        )
    ).one()
    last_out = None
    if last is not None:
        last_out = {
            "job_name": last.job_name,
            "status": last.status,
            "started_at": last.started_at.isoformat() if last.started_at else None,
            "finished_at": last.finished_at.isoformat() if last.finished_at else None,
        }
    return {
        "last_run": last_out,
        "prompts": prompts,
        "conversations": conversations,
        "licensed_users": licensed,
        "directory_users": directory,
        "earliest_prompt": span[0].isoformat() if span[0] else None,
        "latest_prompt": span[1].isoformat() if span[1] else None,
    }
