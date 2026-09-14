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

# App mix weighted to look like a real tenant — Teams and Word dominate.
_APPS = [
    ("Microsoft Teams", 30),
    ("Word", 20),
    ("Outlook", 18),
    ("PowerPoint", 10),
    ("Excel", 8),
    ("Copilot Chat", 7),
    ("OneNote", 3),
    ("Loop", 2),
    ("SharePoint", 2),
]
_CHAT_TYPES = ["groupChat", "oneOnOne", "meeting", "channel"]
_CONVERSATION_TYPES = ["appchat", "webchat", "inline"]


def _weighted_app(rng: random.Random) -> str:
    names = [a for a, _ in _APPS]
    weights = [w for _, w in _APPS]
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


async def seed(days: int = 45, users: int = 40, reset: bool = True) -> dict[str, int]:
    """Populate the usage tables with plausible fictional data.

    Returns a stats dict so callers (CLI and the admin endpoint) can report
    what was created.
    """
    rng = random.Random(20260914)

    directory = _make_users(rng, users)
    licensed = [u for u in directory if u.has_copilot_license]
    today = date.today()
    now = datetime.now(timezone.utc)

    prompts: list[Prompt] = []
    conversations = 0

    for day_offset in range(days):
        day = today - timedelta(days=day_offset)
        # Weekends are quiet; recent weeks are busier than older ones so the
        # trend lines have a visible upward slope.
        if day.weekday() >= 5:
            active_share = 0.12
        else:
            ramp = 1.0 - (day_offset / (days * 1.6))
            active_share = 0.55 * max(0.35, ramp)

        for user in licensed:
            if rng.random() > active_share:
                continue
            for _ in range(rng.randint(1, 4)):
                conversations += 1
                conversation_id = str(uuid.uuid4())
                app = _weighted_app(rng)
                chat_type = rng.choice(_CHAT_TYPES) if app == "Microsoft Teams" else None
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
                            file_location=None,
                            teams_location="Teams" if app == "Microsoft Teams" else None,
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
