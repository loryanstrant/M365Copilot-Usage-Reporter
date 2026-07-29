"""Re-derive parsed columns on existing ``prompts`` rows from their ``raw_json``.

Use after changing the ingest transforms (e.g. location categorisation) so the
already-stored interactions get the corrected values without re-calling Graph.

Usage: python scripts/rederive_prompts.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from shared.db import SessionLocal
from shared.models import Prompt
from worker.transforms import (
    derive_chat_type,
    derive_conversation_location,
    extract_locations,
    normalise_app_name,
    strip_app_prefix,
)


async def rederive() -> None:
    updated = 0
    async with SessionLocal() as session:
        rows = (await session.execute(select(Prompt))).scalars().all()
        for p in rows:
            raw = p.raw_json or {}
            app_class = strip_app_prefix(raw.get("appClass"))
            conversation_type = raw.get("conversationType")
            file_location, teams_location = extract_locations(raw.get("contexts"))
            p.app_name = normalise_app_name(app_class)
            p.conversation_location = derive_conversation_location(conversation_type)
            p.chat_type = derive_chat_type(conversation_type, app_class)
            p.file_location = file_location
            p.teams_location = teams_location
            updated += 1
        await session.commit()
    print(f"Re-derived {updated} prompt rows.")


if __name__ == "__main__":
    asyncio.run(rederive())
