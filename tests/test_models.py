"""Schema/model smoke tests (SQLite)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from shared.models import AppConfig, Prompt


async def test_prompt_roundtrip(session):
    session.add(
        Prompt(
            prompt_id="p1",
            user_id="u1",
            conversation_id="c1",
            app_name="Copilot Chat",
            prompt_date=date(2026, 1, 1),
            conversation_location="Chat",
            chat_type="Work",
            raw_json={"id": "p1"},
        )
    )
    await session.commit()

    count = await session.scalar(select(func.count()).select_from(Prompt))
    assert count == 1

    got = await session.scalar(select(Prompt).where(Prompt.prompt_id == "p1"))
    assert got is not None
    assert got.conversation_id == "c1"
    assert got.raw_json == {"id": "p1"}


async def test_app_config_defaults(session):
    cfg = AppConfig(id=1, copilot_sku_ids=["639dec6b-bb19-468b-871c-c5c441c4b0cb"])
    session.add(cfg)
    await session.commit()

    got = await session.get(AppConfig, 1)
    assert got is not None
    assert "639dec6b-bb19-468b-871c-c5c441c4b0cb" in got.copilot_sku_ids
