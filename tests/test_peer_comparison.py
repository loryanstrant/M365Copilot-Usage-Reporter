"""You vs your team vs your organisation.

The load-bearing claim is the disclosure rule. "Aggregates only" stops being
true at small n: with two people in a team, the team mean and your own figure
give the other person's exact number. So the team series is withheld below a
threshold rather than drawn from a group small enough to identify someone.
"""
from __future__ import annotations

from datetime import date

import pytest

from api import metrics
from api.filters import MetricFilters
from api.metrics import MIN_TEAM_PEERS
from shared.db import SessionLocal
from shared.models import EntraUser, Prompt

ME = "user-me"


async def _person(uid: str, dept: str | None, prompts: int, *, manager: str | None = None,
                  apps: tuple[str, ...] = ("Teams",)) -> None:
    async with SessionLocal() as s:
        s.add(
            EntraUser(
                user_id=uid, upn=f"{uid}@demo.local", display_name=uid,
                department=dept, manager_id=manager, has_copilot_license=True,
            )
        )
        for i in range(prompts):
            s.add(
                Prompt(
                    prompt_id=f"{uid}-{i}",
                    user_id=uid,
                    conversation_id=f"{uid}-c{i // 2}",
                    app_name=apps[i % len(apps)],
                    prompt_date=date(2026, 9, 1),
                )
            )
        await s.commit()


async def _compare() -> dict:
    async with SessionLocal() as s:
        return await metrics.peer_comparison(s, user_id=ME, filters=MetricFilters())


# --------------------------------------------------------------------------- #
# The disclosure rule
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_team_of_two_does_not_get_a_team_series():
    """The case that leaks: my figure plus the mean gives the other person's."""
    await _person(ME, "Finance", 10)
    await _person("other", "Finance", 4)
    body = await _compare()
    assert body["team"] is None
    assert body["mine"]["prompts"] == 10


@pytest.mark.asyncio
async def test_a_team_just_below_the_threshold_is_withheld():
    await _person(ME, "Finance", 10)
    for i in range(MIN_TEAM_PEERS - 1):
        await _person(f"p{i}", "Finance", 4)
    body = await _compare()
    assert body["team"] is None
    assert body["team_size"] == MIN_TEAM_PEERS - 1


@pytest.mark.asyncio
async def test_a_team_at_the_threshold_is_shown():
    await _person(ME, "Finance", 10)
    for i in range(MIN_TEAM_PEERS):
        await _person(f"p{i}", "Finance", 4)
    body = await _compare()
    assert body["team"] is not None
    assert body["team"]["prompts"] == 4
    assert body["team_label"] == "Finance"


@pytest.mark.asyncio
async def test_a_department_of_one_is_not_an_error():
    await _person(ME, "Legal", 7)
    for i in range(6):
        await _person(f"o{i}", "Sales", 3)
    body = await _compare()
    assert body["team"] is None
    assert body["organisation"]["prompts"] == 3


# --------------------------------------------------------------------------- #
# Why the team is withheld, which is not the same question as whether it is
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_department_of_one_reports_too_small_not_unknown():
    """The bug this pins: both cases have zero peers, and inferring the reason
    from that count tells somebody whose department is on file that we do not
    know which team they are in. That is untrue about their own data, and it
    sends an administrator looking for the wrong problem."""
    await _person(ME, "Legal", 7)
    for i in range(6):
        await _person(f"o{i}", "Sales", 3)
    body = await _compare()
    assert body["team_state"] == "too_small"
    assert body["team_label"] == "Legal"
    assert body["team_size"] == 0


@pytest.mark.asyncio
async def test_no_department_and_no_manager_reports_unknown():
    await _person(ME, None, 7)
    for i in range(6):
        await _person(f"o{i}", "Sales", 3)
    body = await _compare()
    assert body["team_state"] == "unknown"
    assert body["team_label"] is None


@pytest.mark.asyncio
async def test_a_shown_team_says_so():
    await _person(ME, "Finance", 10)
    for i in range(MIN_TEAM_PEERS):
        await _person(f"p{i}", "Finance", 4)
    body = await _compare()
    assert body["team_state"] == "shown"


@pytest.mark.asyncio
async def test_the_manager_fallback_never_makes_the_group_smaller():
    """A department of three replaced by a manager group of one loses the larger
    grouping and gets no closer to the floor."""
    await _person(ME, "Finance", 10, manager="mgr-1")
    for i in range(3):
        await _person(f"d{i}", "Finance", 4, manager="mgr-2")
    body = await _compare()
    assert body["team_size"] == 3
    assert body["team_label"] == "Finance"
    assert body["team_state"] == "too_small"


@pytest.mark.asyncio
async def test_a_manager_on_file_with_nobody_under_them_is_too_small():
    """The mirror of a department of one, reached down the manager path. A
    manager is on file, so the grouping is identified; it just holds nobody."""
    await _person(ME, None, 7, manager="mgr-alone")
    for i in range(6):
        await _person(f"o{i}", "Sales", 3, manager="mgr-other")
    body = await _compare()
    assert body["team_state"] == "too_small"
    assert body["team_size"] == 0
    assert body["team"] is None


@pytest.mark.asyncio
async def test_the_floor_is_reported_so_the_page_need_not_hardcode_it():
    await _person(ME, "Legal", 1)
    body = await _compare()
    assert body["min_team_peers"] == MIN_TEAM_PEERS


@pytest.mark.asyncio
async def test_no_department_falls_back_to_the_manager_group():
    await _person(ME, None, 10, manager="mgr-1")
    for i in range(MIN_TEAM_PEERS):
        await _person(f"p{i}", None, 6, manager="mgr-1")
    body = await _compare()
    assert body["team"] is not None
    assert body["team"]["prompts"] == 6


@pytest.mark.asyncio
async def test_the_viewer_is_excluded_from_their_own_comparison():
    """Otherwise a heavy user drags up the average they are measured against."""
    await _person(ME, "Finance", 100)
    for i in range(MIN_TEAM_PEERS):
        await _person(f"p{i}", "Finance", 2)
    body = await _compare()
    assert body["team"]["prompts"] == 2
    assert body["organisation"]["prompts"] == 2


# --------------------------------------------------------------------------- #
# The measures
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_apps_used_counts_distinct_apps_per_person():
    await _person(ME, "Finance", 6, apps=("Teams", "Word", "Excel"))
    for i in range(MIN_TEAM_PEERS):
        await _person(f"p{i}", "Finance", 2, apps=("Teams",))
    body = await _compare()
    assert body["mine"]["apps"] == 3
    assert body["team"]["apps"] == 1


@pytest.mark.asyncio
async def test_percentile_is_against_the_organisation():
    """Not against the team: in a team of four it would say more about the team
    than the person."""
    await _person(ME, "Finance", 100)
    for i in range(9):
        await _person(f"p{i}", "Finance", 1)
    body = await _compare()
    assert body["percentile"]["prompts"] == 100
    assert body["organisation_size"] == 9


@pytest.mark.asyncio
async def test_all_series_report_the_window_they_used():
    await _person(ME, "Finance", 3)
    async with SessionLocal() as s:
        body = await metrics.peer_comparison(
            s,
            user_id=ME,
            filters=MetricFilters(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30)),
        )
    assert body["period_from"] == "2026-09-01"
    assert body["period_to"] == "2026-09-30"


@pytest.mark.asyncio
async def test_a_person_with_no_activity_still_gets_a_comparison():
    for i in range(MIN_TEAM_PEERS + 1):
        await _person(f"p{i}", "Finance", 5)
    async with SessionLocal() as s:
        body = await metrics.peer_comparison(s, user_id="nobody", filters=MetricFilters())
    assert body["mine"]["prompts"] == 0
    assert body["organisation"]["prompts"] == 5


@pytest.mark.asyncio
async def test_with_no_filter_the_period_is_the_span_the_data_covers():
    """"The selected period" tells a reader nothing. With no explicit filter the
    panel should still be able to name the window the numbers describe."""
    async with SessionLocal() as s:
        s.add(EntraUser(user_id=ME, upn="me@demo.local", display_name="me"))
        s.add(Prompt(prompt_id="a", user_id=ME, app_name="Teams", prompt_date=date(2026, 8, 3)))
        s.add(Prompt(prompt_id="b", user_id=ME, app_name="Teams", prompt_date=date(2026, 9, 14)))
        await s.commit()
    body = await _compare()
    assert body["period_from"] == "2026-08-03"
    assert body["period_to"] == "2026-09-14"
