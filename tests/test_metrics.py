"""Deterministic metrics tests against a seeded dataset.

Locks the SQL measures so refactors can't silently change the numbers.
"""
from __future__ import annotations

from datetime import date

import pytest

from api import metrics
from shared.models import EntraUser, LicenseCount, LicensedUser, Prompt

TODAY = date(2026, 7, 29)


def _prompt(pid: str, uid: str, cid: str, app: str, d: date) -> Prompt:
    return Prompt(
        prompt_id=pid,
        user_id=uid,
        conversation_id=cid,
        app_name=app,
        prompt_date=d,
    )


@pytest.fixture
async def seeded(session):
    # user-1: 3 prompts across 2 conversations, recent (active)
    session.add_all(
        [
            _prompt("p1", "user-1", "c1", "Copilot Chat", date(2026, 7, 20)),
            _prompt("p2", "user-1", "c1", "Copilot Chat", date(2026, 7, 20)),
            _prompt("p3", "user-1", "c2", "Teams", date(2026, 7, 25)),
            # user-2: 1 prompt, 1 conversation, recent
            _prompt("p4", "user-2", "c3", "Copilot Chat", date(2026, 7, 10)),
            # user-3: old prompt only (inactive: >30 days ago)
            _prompt("p5", "user-3", "c4", "Word", date(2026, 5, 1)),
        ]
    )
    # 4 licensed users: user-1, user-2, user-3 active-ish, user-4 never used
    session.add_all(
        [LicensedUser(user_id=f"user-{i}") for i in range(1, 5)]
    )
    session.add_all(
        [
            EntraUser(user_id="user-1", display_name="Alice", department="Sales",
                      has_copilot_license=True),
            EntraUser(user_id="user-2", display_name="Bob", department="Eng",
                      has_copilot_license=True),
        ]
    )
    session.add(
        LicenseCount(
            recorded_date=TODAY, status="Enabled", enabled=100, allocated=4,
            available=96,
        )
    )
    await session.commit()
    return session


@pytest.mark.asyncio
async def test_summary(seeded):
    s = await metrics.summary(seeded, today=TODAY)
    assert s["prompts"] == 5
    assert s["conversations"] == 4
    assert s["avg_prompts_per_conversation"] == 1.25
    # active within 30 days of 2026-07-29: user-1, user-2 (user-3 is 2026-05-01)
    assert s["active_users"] == 2
    assert s["licensed_users"] == 4
    assert s["adoption_rate"] == 0.5
    assert s["license_enabled"] == 100
    assert s["license_available"] == 96


@pytest.mark.asyncio
async def test_daily_trend(seeded):
    rows = await metrics.daily(seeded)
    by_date = {r["date"]: r for r in rows}
    assert by_date["2026-07-20"]["prompts"] == 2
    assert by_date["2026-07-20"]["conversations"] == 1
    assert by_date["2026-07-25"]["prompts"] == 1


@pytest.mark.asyncio
async def test_conversations_count_null_sessions(session):
    """Session-less prompts (NULL conversation_id) must each count as their own
    conversation, not be dropped from COUNT(DISTINCT) — the bug behind impossible
    prompt:conversation ratios."""
    d = date(2026, 7, 22)
    session.add_all([
        _prompt("np1", "user-1", None, "Word", d),
        _prompt("np2", "user-1", None, "Excel", d),
        _prompt("np3", "user-1", None, "PowerPoint", d),
        # Two prompts that DO share a real session -> one conversation.
        _prompt("sp1", "user-2", "sess-1", "Copilot Chat", d),
        _prompt("sp2", "user-2", "sess-1", "Copilot Chat", d),
    ])
    await session.commit()

    s = await metrics.summary(session, today=date(2026, 7, 29))
    assert s["prompts"] == 5
    # 3 session-less (each its own) + 1 shared session = 4 conversations.
    assert s["conversations"] == 4

    rows = await metrics.daily(session)
    day = {r["date"]: r for r in rows}["2026-07-22"]
    assert day["prompts"] == 5
    assert day["conversations"] == 4


@pytest.mark.asyncio
async def test_by_app(seeded):
    rows = await metrics.by_app(seeded, today=TODAY)
    apps = {r["app_name"]: r for r in rows}
    assert apps["Copilot Chat"]["prompts"] == 3
    assert apps["Copilot Chat"]["conversations"] == 2
    assert apps["Copilot Chat"]["users"] == 2
    assert apps["Word"]["days_since_last"] == (TODAY - date(2026, 5, 1)).days


@pytest.mark.asyncio
async def test_by_app_daily(seeded):
    rows = await metrics.by_app_daily(seeded)
    # Rows are per app per day; Copilot Chat has two prompts on 2026-07-20 (c1)
    # and one on 2026-07-10 (c3).
    cc = {r["date"]: r for r in rows if r["app_name"] == "Copilot Chat"}
    assert cc["2026-07-20"]["prompts"] == 2
    assert cc["2026-07-20"]["conversations"] == 1
    assert cc["2026-07-10"]["prompts"] == 1
    teams = [r for r in rows if r["app_name"] == "Teams"]
    assert teams == [
        {"app_name": "Teams", "date": "2026-07-25", "prompts": 1, "conversations": 1}
    ]


@pytest.mark.asyncio
async def test_by_user_leaderboard(seeded):
    rows = await metrics.by_user(seeded, today=TODAY)
    assert rows[0]["user_id"] == "user-1"  # most prompts first
    assert rows[0]["display_name"] == "Alice"
    assert rows[0]["prompts"] == 3
    assert rows[0]["conversations"] == 2


@pytest.mark.asyncio
async def test_categories_buckets(seeded):
    rows = await metrics.categories(seeded, today=TODAY)
    buckets = {r["category"]: r["users"] for r in rows}
    # last-30-day counts: user-1=3, user-2=1, user-3=0, user-4=0
    assert buckets["0"] == 2
    assert buckets["<10"] == 2
    assert buckets["10-50"] == 0


@pytest.mark.asyncio
async def test_active_inactive(seeded):
    res = await metrics.active_inactive(seeded, today=TODAY)
    assert res["licensed"] == 4
    assert res["active"] == 2
    assert res["inactive"] == 2


@pytest.mark.asyncio
async def test_briefing(seeded):
    b = await metrics.briefing(seeded, today=TODAY)
    assert b["window_days"] == 30
    assert b["period_start"] == "2026-06-29"
    assert b["period_end"] == "2026-07-29"
    # Current 30d: p1,p2,p3,p4 (p5 on 2026-05-01 is outside); previous 30d: none.
    assert b["current"] == {"prompts": 4, "conversations": 3, "active_users": 2}
    assert b["previous"] == {"prompts": 0, "conversations": 0, "active_users": 0}
    assert b["licensed_users"] == 4
    assert b["inactive_users"] == 2
    assert b["adoption_rate"] == 0.5
    assert b["top_apps"][0] == {"name": "Copilot Chat", "prompts": 3, "prev_prompts": 0}
    assert b["top_departments"][0] == {"name": "Sales", "prompts": 3}


@pytest.mark.asyncio
async def test_licenses(seeded):
    rows = await metrics.licenses(seeded)
    assert rows == [
        {"date": "2026-07-29", "enabled": 100, "allocated": 4, "available": 96}
    ]
