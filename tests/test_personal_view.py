"""Personal view and the organisation-view gate.

The security-relevant claims here are:

- a personal endpoint scopes to the caller's own object ID, and offers no way to
  ask for somebody else's;
- the organisation view is closed to people outside the configured group;
- but an unconfigured group leaves the org view open, so upgrading an existing
  deployment doesn't lock everyone out.
"""
from __future__ import annotations

from datetime import date

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from api.auth import create_access_token
from shared.db import SessionLocal
from shared.models import AppConfig, AppUser, Prompt
from shared.security import hash_password

ME = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SOMEONE_ELSE = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
GROUP = "cccccccc-cccc-cccc-cccc-cccccccccccc"


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _seed_prompts() -> None:
    """Two people with clearly different volumes, so a leak is obvious."""
    async with SessionLocal() as s:
        for i in range(3):
            s.add(
                Prompt(
                    prompt_id=f"mine-{i}",
                    user_id=ME,
                    app_name="Teams",
                    prompt_date=date(2026, 9, 1),
                )
            )
        for i in range(9):
            s.add(
                Prompt(
                    prompt_id=f"theirs-{i}",
                    user_id=SOMEONE_ELSE,
                    app_name="Word",
                    prompt_date=date(2026, 9, 1),
                )
            )
        await s.commit()


async def _set_org_group(group_id: str | None) -> None:
    async with SessionLocal() as s:
        cfg = await s.get(AppConfig, 1)
        if cfg is None:
            cfg = AppConfig(id=1)
            s.add(cfg)
        cfg.org_view_group_id = group_id
        await s.commit()


def _viewer_headers(oid: str = ME) -> dict[str, str]:
    token = create_access_token("me@contoso.com", "viewer", oid=oid, upn="me@contoso.com")
    return {"Authorization": f"Bearer {token}"}


async def _admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --------------------------------------------------------------------------- #
# Personal view
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_personal_summary_counts_only_my_own_activity(client):
    await _seed_prompts()
    r = await client.get("/metrics/me/summary", headers=_viewer_headers())
    assert r.status_code == 200
    # Three of mine, nine of theirs. Anything above 3 means a leak.
    assert r.json()["prompts"] == 3


@pytest.mark.asyncio
async def test_personal_view_cannot_be_pointed_at_someone_else(client):
    """The caller is taken from the token, so a spoofed filter changes nothing."""
    await _seed_prompts()
    r = await client.get(
        f"/metrics/me/summary?user_id={SOMEONE_ELSE}",
        headers=_viewer_headers(),
    )
    assert r.status_code == 200
    assert r.json()["prompts"] == 3


@pytest.mark.asyncio
async def test_personal_view_is_absent_without_an_entra_identity(client):
    """The password admin has no object ID, so there is nothing to show them."""
    headers = await _admin_headers(client)
    r = await client.get("/metrics/me/summary", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_comparison_reports_the_median_not_individuals(client):
    await _seed_prompts()
    r = await client.get("/metrics/me/comparison", headers=_viewer_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["my_prompts"] == 3
    assert body["people_counted"] == 2
    # No other person's identity or figures should appear anywhere.
    assert SOMEONE_ELSE not in r.text


@pytest.mark.asyncio
async def test_personal_view_requires_authentication(client):
    r = await client.get("/metrics/me/summary")
    assert r.status_code in (401, 403)


# --------------------------------------------------------------------------- #
# Organisation-view gate
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_org_view_open_when_no_group_configured(client):
    """Upgrades must not silently lock existing viewers out."""
    await _seed_prompts()
    await _set_org_group(None)
    r = await client.get("/metrics/summary", headers=_viewer_headers())
    assert r.status_code == 200
    assert r.json()["prompts"] == 12


@pytest.mark.asyncio
async def test_org_view_denied_to_non_members(client):
    await _seed_prompts()
    await _set_org_group(GROUP)
    r = await client.get("/metrics/summary", headers=_viewer_headers())
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_org_view_allowed_for_group_members(client, monkeypatch):
    await _seed_prompts()
    await _set_org_group(GROUP)

    import api.oidc as oidc

    async def _member(principal, group_id, session):
        return group_id == GROUP

    monkeypatch.setattr(oidc, "is_group_member", _member)
    r = await client.get("/metrics/summary", headers=_viewer_headers())
    assert r.status_code == 200
    assert r.json()["prompts"] == 12


@pytest.mark.asyncio
async def test_admin_bypasses_the_org_group(client):
    await _seed_prompts()
    await _set_org_group(GROUP)
    headers = await _admin_headers(client)
    r = await client.get("/metrics/summary", headers=headers)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_personal_view_survives_the_org_gate(client):
    """Losing org access must not cost someone their own data."""
    await _seed_prompts()
    await _set_org_group(GROUP)
    headers = _viewer_headers()
    assert (await client.get("/metrics/summary", headers=headers)).status_code == 403
    r = await client.get("/metrics/me/summary", headers=headers)
    assert r.status_code == 200
    assert r.json()["prompts"] == 3


@pytest.mark.asyncio
async def test_auth_me_advertises_capabilities(client):
    await _set_org_group(GROUP)
    r = await client.get("/auth/me", headers=_viewer_headers())
    body = r.json()
    assert body["has_personal_view"] is True
    assert body["can_view_org"] is False


@pytest.mark.asyncio
async def test_shared_lookups_stay_open_to_everyone(client):
    """Freshness and About sit outside the org gate — every signed-in user needs them."""
    await _set_org_group(GROUP)
    headers = _viewer_headers()
    assert (await client.get("/metrics/freshness", headers=headers)).status_code == 200
    assert (await client.get("/metrics/about", headers=headers)).status_code == 200
