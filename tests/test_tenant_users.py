"""The tenant users listing.

It joins three things people otherwise export separately and match by hand:
who is in the directory, who holds a Copilot licence, and how much each person
has actually used it.
"""
from __future__ import annotations

from datetime import date

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from shared.db import SessionLocal
from shared.models import AppUser, EntraUser, Prompt
from shared.security import hash_password


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _seed() -> None:
    async with SessionLocal() as s:
        s.add(
            EntraUser(
                user_id="mgr-1",
                upn="jordan@contoso.com",
                display_name="Jordan Webb",
                department="Finance",
                has_copilot_license=True,
            )
        )
        s.add(
            EntraUser(
                user_id="u-1",
                upn="avery@contoso.com",
                display_name="Avery Coleman",
                job_title="Analyst",
                department="Finance",
                office_location="Melbourne",
                manager_id="mgr-1",
                has_copilot_license=True,
            )
        )
        s.add(
            EntraUser(
                user_id="u-2",
                upn="blake@contoso.com",
                display_name="Blake Nguyen",
                department="Technology",
                has_copilot_license=False,
            )
        )
        for i in range(3):
            s.add(
                Prompt(
                    prompt_id=f"p{i}",
                    user_id="u-1",
                    app_name="Teams",
                    prompt_date=date(2026, 9, 1),
                )
            )
        await s.commit()


@pytest.mark.asyncio
async def test_lists_directory_users_with_their_prompt_counts(client):
    await _seed()
    r = await client.get("/metrics/users", headers=await _admin_headers(client))
    assert r.status_code == 200, r.text
    by_upn = {u["user_principal_name"]: u for u in r.json()}

    avery = by_upn["avery@contoso.com"]
    assert avery["prompts"] == 3
    assert avery["has_copilot_license"] is True
    assert avery["department"] == "Finance"


@pytest.mark.asyncio
async def test_a_user_with_no_activity_still_appears(client):
    """The whole point is spotting a licence nobody is using."""
    await _seed()
    r = await client.get("/metrics/users", headers=await _admin_headers(client))
    by_upn = {u["user_principal_name"]: u for u in r.json()}
    assert by_upn["jordan@contoso.com"]["prompts"] == 0
    assert by_upn["jordan@contoso.com"]["has_copilot_license"] is True


@pytest.mark.asyncio
async def test_the_manager_is_resolved_to_a_name(client):
    """manager_id is a GUID; a listing showing GUIDs is no use to anyone."""
    await _seed()
    r = await client.get("/metrics/users", headers=await _admin_headers(client))
    by_upn = {u["user_principal_name"]: u for u in r.json()}
    assert by_upn["avery@contoso.com"]["manager_name"] == "Jordan Webb"
    assert by_upn["jordan@contoso.com"]["manager_name"] is None


@pytest.mark.asyncio
async def test_listing_is_organisation_data_and_needs_the_org_gate(client):
    """It is a list of named colleagues, so it must not be open to everyone."""
    await _seed()
    r = await client.get("/metrics/users")
    assert r.status_code == 401
