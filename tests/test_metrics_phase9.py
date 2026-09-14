"""Phase 9 metrics: dimensional filters + new measures (locations, rollups,
laggards, chat types, CopilotScore, filter options)."""
from __future__ import annotations

from datetime import date

import pytest

from api import metrics
from api.filters import MetricFilters
from shared.models import EntraUser, LicensedUser, Prompt

TODAY = date(2026, 7, 29)


def _p(
    pid: str,
    uid: str,
    cid: str,
    app: str,
    d: date,
    *,
    chat_type: str | None = None,
    conversation_location: str | None = None,
    teams_location: str | None = None,
    file_location: str | None = None,
) -> Prompt:
    return Prompt(
        prompt_id=pid,
        user_id=uid,
        conversation_id=cid,
        app_name=app,
        prompt_date=d,
        chat_type=chat_type,
        conversation_location=conversation_location,
        teams_location=teams_location,
        file_location=file_location,
    )


@pytest.fixture
async def seeded(session):
    session.add_all(
        [
            _p("p1", "user-1", "c1", "Copilot Chat", date(2026, 7, 20),
               chat_type="Work", conversation_location="Chat"),
            _p("p2", "user-1", "c1", "Copilot Chat", date(2026, 7, 21),
               chat_type="Work", conversation_location="Chat"),
            _p("p3", "user-1", "c2", "Teams", date(2026, 7, 25),
               chat_type="Work", conversation_location="App", teams_location="Standup"),
            _p("p4", "user-2", "c3", "Copilot Chat", date(2026, 7, 10),
               chat_type="Web", conversation_location="App"),
            _p("p5", "user-3", "c4", "Word", date(2026, 5, 1),
               conversation_location="App", file_location="/site/report.docx"),
        ]
    )
    session.add_all([LicensedUser(user_id=f"user-{i}") for i in range(1, 5)])
    session.add_all(
        [
            EntraUser(user_id="user-1", display_name="Alice", department="Sales",
                      office_location="Sydney", manager_id="mgr-1",
                      has_copilot_license=True),
            EntraUser(user_id="user-2", display_name="Bob", department="Eng",
                      office_location="Melbourne", manager_id="mgr-1",
                      has_copilot_license=True),
            EntraUser(user_id="user-3", display_name="Cara", department="Sales",
                      office_location="Sydney", manager_id="mgr-2",
                      has_copilot_license=True),
            EntraUser(user_id="user-4", display_name="Dan", department="Eng",
                      office_location="Melbourne", manager_id="mgr-2",
                      has_copilot_license=True),
            EntraUser(user_id="mgr-1", display_name="Manager One"),
            EntraUser(user_id="mgr-2", display_name="Manager Two"),
        ]
    )
    await session.commit()
    return session


@pytest.mark.asyncio
async def test_summary_filtered_by_department(seeded):
    s = await metrics.summary(
        seeded, filters=MetricFilters(departments=["Sales"]), today=TODAY
    )
    # Sales = user-1 (3 prompts, c1+c2) + user-3 (1 prompt, c4) = 4 prompts / 3 convs
    assert s["prompts"] == 4
    assert s["conversations"] == 3


@pytest.mark.asyncio
async def test_summary_filtered_by_chat_type(seeded):
    s = await metrics.summary(seeded, filters=MetricFilters(chat_types=["Web"]))
    assert s["prompts"] == 1


@pytest.mark.asyncio
async def test_summary_multi_select_apps(seeded):
    # Deselecting "Word" -> include only Copilot Chat + Teams = 4 prompts.
    s = await metrics.summary(
        seeded, filters=MetricFilters(apps=["Copilot Chat", "Teams"])
    )
    assert s["prompts"] == 4


@pytest.mark.asyncio
async def test_locations_splits(seeded):
    res = await metrics.locations(seeded)
    chat = {r["name"]: r["prompts"] for r in res["chat_types"]}
    assert chat["Work"] == 3
    assert chat["Web"] == 1
    locs = {r["name"]: r["prompts"] for r in res["conversation_locations"]}
    assert locs["Chat"] == 2
    assert locs["App"] == 3
    teams = {r["name"]: r["prompts"] for r in res["teams_locations"]}
    assert teams["Standup"] == 1
    assert any(t["chat_type"] == "Work" for t in res["daily_by_chat_type"])


@pytest.mark.asyncio
async def test_leaderboard_rollups(seeded):
    res = await metrics.leaderboard_rollups(seeded, limit=5)
    depts = {r["name"]: r["prompts"] for r in res["departments"]}
    assert depts["Sales"] == 4
    assert depts["Eng"] == 1
    offices = {r["name"]: r["prompts"] for r in res["offices"]}
    assert offices["Sydney"] == 4
    managers = {r["name"]: r["prompts"] for r in res["managers"]}
    assert managers["Manager One"] == 4  # mgr-1 = user-1(3) + user-2(1)
    assert managers["Manager Two"] == 1


@pytest.mark.asyncio
async def test_laggards(seeded):
    res = await metrics.laggards(seeded, today=TODAY)
    ids = {u["user_id"] for u in res["users"] if u["inactive"]}
    assert ids == {"user-3", "user-4"}  # no prompt in last 30 days
    dept_idle = {d["name"]: d["inactive_users"] for d in res["top_departments"]}
    assert dept_idle["Sales"] == 1  # user-3
    assert dept_idle["Eng"] == 1  # user-4


@pytest.mark.asyncio
async def test_chat_types(seeded):
    res = await metrics.chat_types(seeded)
    chat = {r["name"]: r["prompts"] for r in res["chat_types"]}
    assert chat == {"Work": 3, "Web": 1}


@pytest.mark.asyncio
async def test_coaching_pairs_by_department(seeded):
    res = await metrics.coaching_pairs(seeded, group_by="department", today=TODAY)
    groups = {g["name"]: g for g in res["groups"]}

    # Dan has never used Copilot but must still appear: the prompt join is a
    # LEFT JOIN, so zero-usage licensed users are exactly what we surface.
    eng = groups["Eng"]
    assert eng["licensed"] == 2 and eng["active"] == 1 and eng["inactive"] == 1
    assert [p["laggard"]["display_name"] for p in eng["pairs"]] == ["Dan"]
    assert [p["leader"]["display_name"] for p in eng["pairs"]] == ["Bob"]
    assert eng["pairs"][0]["gap"] == 1

    # Sales is evenly spread (3 vs 1, both active) so there is nothing to pair.
    assert groups["Sales"]["pairs"] == []
    assert res["totals"]["pairs"] == 1
    assert res["group_label"] == "Department"


@pytest.mark.asyncio
async def test_coaching_pairs_by_manager_uses_manager_name(seeded):
    res = await metrics.coaching_pairs(seeded, group_by="manager", today=TODAY)
    groups = {g["name"]: g for g in res["groups"]}
    assert "Manager Two" in groups  # resolved via the manager alias join
    pairs = groups["Manager Two"]["pairs"]
    assert [(p["leader"]["display_name"], p["laggard"]["display_name"]) for p in pairs] == [
        ("Cara", "Dan")
    ]


@pytest.mark.asyncio
async def test_coaching_pairs_filters_do_not_drop_zero_usage_users(seeded):
    """A prompt-level filter must narrow the counts without hiding laggards."""
    res = await metrics.coaching_pairs(
        seeded,
        filters=MetricFilters(apps=["Word"]),
        group_by="department",
        today=TODAY,
    )
    groups = {g["name"]: g for g in res["groups"]}
    # Only Cara used Word, so within Sales she becomes the leader and Alice —
    # who has prompts, but none in Word — becomes the laggard.
    sales = groups["Sales"]
    assert sales["licensed"] == 2
    assert [(p["leader"]["display_name"], p["laggard"]["display_name"]) for p in sales["pairs"]] == [
        ("Cara", "Alice")
    ]
    # Nobody in Eng used Word, so there is no leader to pair with.
    assert groups["Eng"]["pairs"] == []


@pytest.mark.asyncio
async def test_coaching_pairs_metric_toggle(seeded):
    res = await metrics.coaching_pairs(
        seeded, group_by="department", metric="conversations", today=TODAY
    )
    assert res["metric"] == "conversations"
    eng = {g["name"]: g for g in res["groups"]}["Eng"]
    assert eng["pairs"][0]["leader"]["conversations"] == 1
    assert eng["pairs"][0]["laggard"]["conversations"] == 0


def test_copilot_score_ladder():
    assert metrics.copilot_score_from_count(10000) == 100
    assert metrics.copilot_score_from_count(2500) == 25
    assert metrics.copilot_score_from_count(150) == 1
    assert metrics.copilot_score_from_count(50) == 0


@pytest.mark.asyncio
async def test_filter_options(seeded):
    opts = await metrics.filter_options(seeded)
    assert opts["departments"] == ["Eng", "Sales"]
    assert opts["offices"] == ["Melbourne", "Sydney"]
    assert "Work" in opts["chat_types"]
    names = [m["name"] for m in opts["managers"]]
    assert "Manager One" in names and "Manager Two" in names
