"""Evaluating with demo data must reach the personal pages.

The personal view is derived from the token's Entra object ID, and the
password admin has none — so before this, anyone following the deploy guide's
"load demo data to evaluate without a tenant" could read about the personal
pages in the README and never see one.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from shared.db import SessionLocal
from shared.demo import DEMO_PERSONA_KEY
from shared.models import AppUser, EntraUser, IngestState, Prompt
from shared.security import hash_password

PERSONA_ID = "11111111-2222-3333-4444-555555555555"


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _add_admin() -> None:
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()


async def _seed_persona() -> None:
    async with SessionLocal() as s:
        s.add(
            EntraUser(
                user_id=PERSONA_ID,
                upn="ruby.chen@demo.local",
                display_name="Ruby Chen",
                has_copilot_license=True,
            )
        )
        for i in range(4):
            s.add(
                Prompt(
                    prompt_id=f"demo-{i}",
                    user_id=PERSONA_ID,
                    app_name="Teams",
                    prompt_date=date(2026, 9, 1),
                )
            )
        s.add(
            IngestState(
                key=DEMO_PERSONA_KEY,
                last_status="seeded",
                last_run_at=datetime.now(timezone.utc),
                detail={
                    "user_id": PERSONA_ID,
                    "upn": "ruby.chen@demo.local",
                    "display_name": "Ruby Chen",
                },
            )
        )
        await s.commit()


async def _login(client: httpx.AsyncClient) -> dict[str, str]:
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_without_demo_data_the_password_admin_has_no_personal_view(client):
    """A live deployment must be completely unaffected."""
    await _add_admin()
    body = (await client.get("/auth/me", headers=await _login(client))).json()
    assert body["has_personal_view"] is False
    assert body["display_name"] is None


@pytest.mark.asyncio
async def test_with_demo_data_the_personal_view_is_reachable(client):
    await _add_admin()
    await _seed_persona()
    headers = await _login(client)

    body = (await client.get("/auth/me", headers=headers)).json()
    assert body["has_personal_view"] is True
    # Signed in as the admin account, but shown as the person being borrowed —
    # so it is visible whose activity is on screen.
    assert body["display_name"] == "Ruby Chen"
    assert body["role"] == "admin"

    r = await client.get("/metrics/me/summary", headers=headers)
    assert r.status_code == 200
    assert r.json()["prompts"] == 4


@pytest.mark.asyncio
async def test_clearing_demo_data_removes_the_binding(client):
    await _add_admin()
    await _seed_persona()

    from scripts.seed_demo import clear

    await clear()
    body = (await client.get("/auth/me", headers=await _login(client))).json()
    assert body["has_personal_view"] is False


@pytest.mark.asyncio
async def test_a_real_ingest_retires_the_demo_persona(client):
    """Once live data arrives, borrowing a fictional identity is misleading."""
    await _add_admin()
    await _seed_persona()

    from shared.db import SessionLocal as SL
    from shared.demo import demo_persona

    async with SL() as s:
        assert await demo_persona(s) is not None

    from worker.ingest import run_ingest
    from shared.models import AppConfig

    async with SL() as s:
        s.add(
            AppConfig(
                id=1,
                tenant_id="t",
                client_id="c",
                client_secret_encrypted="x",
                copilot_sku_ids=[],
            )
        )
        await s.commit()

    class _Graph:
        async def iter_licensed_users(self, sku_ids):
            if False:
                yield {}

        async def get_subscribed_skus(self):
            return []

        async def iter_directory_users(self):
            if False:
                yield {}

        async def iter_enterprise_interactions(self, *a, **k):
            if False:
                yield {}

        async def aclose(self):
            pass

    async with SL() as s:
        cfg = await s.get(AppConfig, 1)
        await run_ingest(SL, graph=_Graph(), config=cfg, job_name="test")

    async with SL() as s:
        assert await demo_persona(s) is None
