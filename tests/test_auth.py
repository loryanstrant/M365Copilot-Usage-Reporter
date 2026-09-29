"""Auth + admin API tests (login, RBAC, config write-only secret)."""
from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager

from api.main import app
from shared.models import AppUser
from shared.security import hash_password


async def _seed_user(session, username: str, password: str, role: str) -> None:
    session.add(
        AppUser(username=username, password_hash=hash_password(password), role=role)
    )
    await session.commit()


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def _login(client: httpx.AsyncClient, username: str, password: str) -> str:
    resp = await client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_login_bad_credentials(session):
    await _seed_user(session, "admin", "secret", "admin")
    async with LifespanManager(app), _client() as client:
        resp = await client.post(
            "/auth/login", json={"username": "admin", "password": "wrong"}
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_config_requires_auth(session):
    async with LifespanManager(app), _client() as client:
        assert (await client.get("/admin/config")).status_code == 401


@pytest.mark.asyncio
async def test_viewer_cannot_write_config(session):
    await _seed_user(session, "viewer", "pw", "viewer")
    async with LifespanManager(app), _client() as client:
        token = await _login(client, "viewer", "pw")
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.put(
            "/admin/config", headers=headers, json={"tenant_id": "t"}
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_config_roundtrip_secret_write_only(session):
    await _seed_user(session, "admin", "pw", "admin")
    async with LifespanManager(app), _client() as client:
        token = await _login(client, "admin", "pw")
        headers = {"Authorization": f"Bearer {token}"}

        # /auth/me reflects the role and what this user can reach. The admin
        # signs in with a password, so there is no Entra identity behind them
        # and therefore no personal view — but they always see org data.
        me = await client.get("/auth/me", headers=headers)
        assert me.json() == {
            "username": "admin",
            "role": "admin",
            # The password admin has no directory identity, so no display name.
            "display_name": None,
            "upn": None,
            "can_view_org": True,
            "has_personal_view": False,
        }

        # Save config including a client secret
        resp = await client.put(
            "/admin/config",
            headers=headers,
            json={
                "tenant_id": "tenant-1",
                "client_id": "client-1",
                "client_secret": "super-secret",
                "copilot_sku_ids": ["sku-a", "sku-b"],
                "backfill_days": 45,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["configured"] is True
        assert body["has_client_secret"] is True
        assert body["backfill_days"] == 45
        assert body["copilot_sku_ids"] == ["sku-a", "sku-b"]
        assert "client_secret" not in body  # secret never returned

        # Re-read: secret still not exposed, values persisted
        got = (await client.get("/admin/config", headers=headers)).json()
        assert got["has_client_secret"] is True
        assert got.get("client_secret") is None
        assert got["tenant_id"] == "tenant-1"

        # Partial update without secret keeps the stored secret
        resp = await client.put(
            "/admin/config", headers=headers, json={"backfill_days": 7}
        )
        assert resp.json()["has_client_secret"] is True
        assert resp.json()["backfill_days"] == 7


@pytest.mark.asyncio
async def test_status_endpoint(session):
    await _seed_user(session, "admin", "pw", "admin")
    async with LifespanManager(app), _client() as client:
        token = await _login(client, "admin", "pw")
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/admin/status", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is False
        assert body["prompts"] == 0
        assert body["last_run"] is None


@pytest.mark.asyncio
async def test_auth_config_reports_the_build_stamp(monkeypatch):
    """The sign-in page shows which build is live.

    Reported here rather than only on the About page because knowing the answer
    matters most when you cannot get in to look — including when you are trying
    to work out whether a deployment actually landed.
    """
    import shared.version as version

    monkeypatch.setattr(version, "BUILD_DATE", "2026-09-30")
    monkeypatch.setattr(version, "BUILD_TIME", "07:57 UTC")
    import api.routers.auth as auth_routes

    monkeypatch.setattr(auth_routes, "BUILD_DATE", "2026-09-30")
    monkeypatch.setattr(auth_routes, "BUILD_TIME", "07:57 UTC")

    async with LifespanManager(app), _client() as client:
        body = (await client.get("/auth/config")).json()
        assert body["build_date"] == "2026-09-30"
        assert body["build_time"] == "07:57 UTC"


@pytest.mark.asyncio
async def test_auth_config_admits_when_there_is_no_stamp(monkeypatch):
    """A local build injects nothing, and must say so rather than invent a date."""
    import api.routers.auth as auth_routes

    monkeypatch.setattr(auth_routes, "BUILD_DATE", None)
    monkeypatch.setattr(auth_routes, "BUILD_TIME", None)

    async with LifespanManager(app), _client() as client:
        body = (await client.get("/auth/config")).json()
        assert body["build_date"] is None
