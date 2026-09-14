"""Seed synthetic Copilot usage data so the dashboards render without live Graph.

Generates a realistic spread of prompts plus the directory, licence and
licence-count rows the reports join against — no Microsoft Graph calls.
Use it to explore the UI locally, or to demo the reporter before wiring up a
tenant.

Run inside the container / venv::

    python -m scripts.seed_demo                  # ~45 days, 40 users
    python -m scripts.seed_demo --days 90 --users 80 --reset

``--reset`` clears the usage/directory tables first. This never touches
credentials (``app_config``) or user accounts (``app_users``).
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete

from shared.db import SessionLocal
from shared.migrate import upgrade_to_head
from shared.models import (
    EntraUser,
    LicenseCount,
    LicensedUser,
    Prompt,
)

_FIRST = [
    "Ava", "Noah", "Mia", "Liam", "Zoe", "Ethan", "Ruby", "Kai", "Isla", "Leo",
    "Nina", "Omar", "Priya", "Sam", "Tara", "Hugo", "Elsie", "Jai", "Maya", "Finn",
]
_LAST = [
    "Bennett", "Okafor", "Nguyen", "Silva", "Kaur", "Murphy", "Chen", "Rossi",
    "Haddad", "Novak", "Osei", "Lindqvist", "Ferreira", "Yamada", "Duarte",
]

_DEPARTMENTS = [
    "Sales", "Marketing", "Finance", "Engineering", "People & Culture",
    "Customer Success", "Legal", "Operations",
]
_OFFICES = ["Sydney", "Melbourne", "Brisbane", "Perth", "Auckland", "Singapore"]
_TITLES = [
    "Account Executive", "Analyst", "Consultant", "Engineer", "Manager",
    "Director", "Coordinator", "Specialist",
]

# The apps that surface Copilot interactions, with a baseline share of the mix
# and a per-app trajectory. Trajectory is a multiplier applied across the window:
# >1 means adoption is climbing over the period, <1 means it is slipping, 1.0 is
# flat. Without this every series is the same global volume curve scaled down,
# so every app appears to move in lockstep — which looks synthetic and hides the
# thing these charts exist to show.
_APPS = [
    # (name, baseline weight, trajectory)
    ("Microsoft Teams", 26, 1.6),
    ("Word", 18, 1.2),
    ("Outlook", 16, 1.0),
    ("Copilot Chat", 12, 2.2),
    ("PowerPoint", 9, 0.45),
    ("Excel", 8, 1.4),
    ("OneNote", 4, 0.3),
    ("Loop", 3, 1.9),
    ("SharePoint", 3, 1.1),
    ("OneDrive", 3, 0.6),
    ("Whiteboard", 2, 0.4),
    ("Forms", 2, 1.3),
    ("Planner", 2, 1.5),
    ("Stream", 2, 0.25),
    ("Viva Engage", 1, 1.2),
    ("Designer", 1, 1.7),
]

# Teams interactions carry where in Teams they happened. Previously every row
# said "Teams", so the breakdown had a single bar and told you nothing.
_TEAMS_LOCATIONS = [("Chat", 50), ("Meetings", 32), ("Channels", 18)]

# Where a referenced file lived. Previously always NULL, so the file-location
# breakdown was permanently empty.
_FILE_LOCATIONS = [("SharePoint", 62), ("OneDrive", 38)]

_CHAT_TYPES = ["groupChat", "oneOnOne", "meeting", "channel"]
_CONVERSATION_TYPES = ["appchat", "webchat", "inline"]

# Apps where referencing a stored document is plausible. Copilot Chat and the
# social/creative surfaces mostly do not, so leaving them out keeps the mix
# believable rather than attaching a file to everything.
_FILE_CAPABLE = {
    "Word", "Excel", "PowerPoint", "OneNote", "Loop",
    "SharePoint", "OneDrive", "Microsoft Teams",
}


def _pick(rng: random.Random, options: list[tuple[str, int]]) -> str:
    return rng.choices([o for o, _ in options], weights=[w for _, w in options], k=1)[0]


def _weighted_app(rng: random.Random, progress: float) -> str:
    """Pick an app, with each app's share shifted by its own trajectory.

    ``progress`` runs 0.0 at the oldest seeded day to 1.0 at today. An app with
    trajectory 2.0 ends the window at roughly twice its starting share; one at
    0.5 ends at half. Interpolating rather than switching keeps the day-to-day
    series smooth instead of stepping.
    """
    names: list[str] = []
    weights: list[float] = []
    for name, base, trajectory in _APPS:
        names.append(name)
        weights.append(base * (1.0 + (trajectory - 1.0) * progress))
    return rng.choices(names, weights=weights, k=1)[0]


def _make_users(rng: random.Random, count: int) -> list[EntraUser]:
    users: list[EntraUser] = []
    seen: set[str] = set()
    for i in range(count):
        first = rng.choice(_FIRST)
        last = rng.choice(_LAST)
        handle = f"{first}.{last}".lower()
        if handle in seen:
            handle = f"{handle}{i}"
        seen.add(handle)
        dept = rng.choice(_DEPARTMENTS)
        # ~75% of the demo population holds a Copilot licence, so the laggards
        # and licence pages have something meaningful to show.
        licensed = rng.random() < 0.75
        users.append(
            EntraUser(
                user_id=str(uuid.uuid4()),
                upn=f"{handle}@demo.local",
                email=f"{handle}@demo.local",
                display_name=f"{first} {last}",
                job_title=rng.choice(_TITLES),
                company_name="Contoso Demo",
                department=dept,
                office_location=rng.choice(_OFFICES),
                country="AU",
                account_enabled=True,
                user_type="Member",
                has_copilot_license=licensed,
            )
        )
    return users


def _adoption_profiles(
    rng: random.Random, licensed: list[EntraUser]
) -> dict[str, float]:
    """Give each licensed person an adoption level, spread within their team.

    Coaching pairs are formed *within* a department: the view needs a heavy user
    and a barely-started one sitting in the same team. Drawing everyone from one
    distribution leaves that to chance, and with a small population most
    departments ended up with neither extreme — which is why the demo only ever
    produced a single pair.

    So the spread is dealt deliberately: every department with enough people gets
    at least one enthusiast and at least one licensed user who has never touched
    Copilot, with the rest in between.
    """
    by_dept: dict[str, list[EntraUser]] = {}
    for user in licensed:
        by_dept.setdefault(user.department or "Unassigned", []).append(user)

    profiles: dict[str, float] = {}
    for members in by_dept.values():
        rng.shuffle(members)
        for position, user in enumerate(members):
            if position == 0 and len(members) >= 3:
                profiles[user.user_id] = rng.uniform(1.6, 2.2)   # champion
            elif position == 1 and len(members) >= 3:
                profiles[user.user_id] = 0.0                     # never started
            elif position == 2 and len(members) >= 6:
                profiles[user.user_id] = rng.uniform(0.15, 0.35)  # struggling
            else:
                profiles[user.user_id] = rng.uniform(0.5, 1.3)
    return profiles


async def seed(days: int = 45, users: int = 90, reset: bool = True) -> dict[str, int]:
    """Populate the usage tables with plausible fictional data.

    Returns a stats dict so callers (CLI and the admin endpoint) can report
    what was created.
    """
    rng = random.Random(20260914)

    directory = _make_users(rng, users)
    licensed = [u for u in directory if u.has_copilot_license]
    profiles = _adoption_profiles(rng, licensed)
    today = date.today()
    now = datetime.now(timezone.utc)

    prompts: list[Prompt] = []
    conversations = 0

    for day_offset in range(days):
        day = today - timedelta(days=day_offset)
        # 0.0 at the oldest seeded day, 1.0 today — drives each app's trajectory.
        progress = 1.0 - (day_offset / max(1, days - 1))
        # Weekends are quiet; recent weeks are busier than older ones so the
        # trend lines have a visible upward slope.
        if day.weekday() >= 5:
            active_share = 0.12
        else:
            ramp = 1.0 - (day_offset / (days * 1.6))
            active_share = 0.55 * max(0.35, ramp)

        for user in licensed:
            # Someone's own adoption level scales their chance of showing up at
            # all, so champions appear most days and the never-started never do.
            appetite = profiles.get(user.user_id, 1.0)
            if appetite <= 0.0 or rng.random() > min(0.95, active_share * appetite):
                continue
            for _ in range(rng.randint(1, 4)):
                conversations += 1
                conversation_id = str(uuid.uuid4())
                app = _weighted_app(rng, progress)
                is_teams = app == "Microsoft Teams"
                chat_type = rng.choice(_CHAT_TYPES) if is_teams else None
                teams_location = _pick(rng, _TEAMS_LOCATIONS) if is_teams else None
                # Not every interaction references a document; roughly half of
                # those that could do, so the breakdown has shape without
                # implying every prompt touches a file.
                file_location = (
                    _pick(rng, _FILE_LOCATIONS)
                    if app in _FILE_CAPABLE and rng.random() < 0.45
                    else None
                )
                for _ in range(rng.randint(1, 5)):
                    prompts.append(
                        Prompt(
                            prompt_id=str(uuid.uuid4()),
                            user_id=user.user_id,
                            conversation_id=conversation_id,
                            app_name=app,
                            prompt_date=day,
                            conversation_type=rng.choice(_CONVERSATION_TYPES),
                            conversation_location=app,
                            chat_type=chat_type,
                            file_location=file_location,
                            teams_location=teams_location,
                            raw_json={"demo": True},
                            ingested_at=now,
                        )
                    )

    licence_counts = []
    for day_offset in range(0, days, 7):
        day = today - timedelta(days=day_offset)
        allocated = len(licensed)
        enabled = allocated + rng.randint(3, 12)
        licence_counts.append(
            LicenseCount(
                recorded_date=day,
                status="Enabled",
                enabled=enabled,
                allocated=allocated,
                available=enabled - allocated,
                suspended=0,
                warning=0,
                locked_out=0,
            )
        )

    async with SessionLocal() as session:
        if reset:
            # Fact/dimension tables only — credentials and app_users are untouched.
            await session.execute(delete(Prompt))
            await session.execute(delete(LicensedUser))
            await session.execute(delete(LicenseCount))
            await session.execute(delete(EntraUser))
            await session.flush()

        session.add_all(directory)
        session.add_all(
            [LicensedUser(user_id=u.user_id, captured_at=now) for u in licensed]
        )
        session.add_all(licence_counts)
        session.add_all(prompts)
        await session.commit()

    return {
        "users": len(directory),
        "licensed_users": len(licensed),
        "conversations": conversations,
        "prompts": len(prompts),
        "days": days,
    }


async def clear() -> dict[str, int]:
    """Remove all seeded usage data, leaving credentials and accounts intact."""
    async with SessionLocal() as session:
        await session.execute(delete(Prompt))
        await session.execute(delete(LicensedUser))
        await session.execute(delete(LicenseCount))
        await session.execute(delete(EntraUser))
        await session.commit()
    return {"cleared": 1}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=45, help="Days of history to generate")
    parser.add_argument("--users", type=int, default=40, help="Directory users to create")
    parser.add_argument("--reset", action="store_true", help="Clear existing data first")
    parser.add_argument("--clear", action="store_true", help="Clear data and exit")
    args = parser.parse_args()

    # psycopg async needs a SelectorEventLoop on Windows (no-op elsewhere).
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Only the CLI runs migrations — the API and worker already migrate on
    # startup, and alembic is synchronous so it must not be called from inside
    # a running event loop.
    upgrade_to_head()

    if args.clear:
        asyncio.run(clear())
        print("Demo data cleared.")
        return 0

    stats = asyncio.run(seed(days=args.days, users=args.users, reset=args.reset))
    print(
        f"Seeded {stats['prompts']} prompts across {stats['conversations']} conversations "
        f"for {stats['licensed_users']} licensed users over {stats['days']} days."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
