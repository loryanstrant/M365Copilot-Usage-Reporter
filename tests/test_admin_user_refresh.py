"""The manual user refresh (POST /admin/users/refresh).

The endpoint exists so an administrator can re-read the directory and licence
lists without waiting for the schedule — the recovery path when licence flags
are missing and Tenant users lists nobody. What matters here is that it is
reachable, that it starts the extraction in the background, and that a second
press while one is in flight answers ``already_running`` rather than starting a
concurrent Graph pull or looking like a failure.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from api.routers import admin as admin_router
from shared.db import SessionLocal
from shared.models import AppUser
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


@pytest.mark.asyncio
async def test_refresh_starts_the_extraction(client, monkeypatch):
    calls: list[object] = []

    async def fake_sync_users(session_factory, **kwargs):
        calls.append(session_factory)
        return {}

    monkeypatch.setattr(admin_router, "sync_users", fake_sync_users)
    monkeypatch.setattr(admin_router, "user_sync_running", lambda: False)

    r = await client.post("/admin/users/refresh", headers=await _admin_headers(client))
    assert r.status_code == 200
    assert r.json()["status"] == "started"
    assert r.json()["detail"]
    # The response returns before the work does; the background task has run by
    # the time the ASGI transport hands control back.
    assert calls


@pytest.mark.asyncio
async def test_second_press_while_running_is_not_an_error(client, monkeypatch):
    """`already_running` is a 200 with its own wording, so the UI can say so plainly."""

    async def fake_sync_users(session_factory, **kwargs):  # pragma: no cover - not reached
        raise AssertionError("a concurrent extraction was started")

    monkeypatch.setattr(admin_router, "sync_users", fake_sync_users)
    monkeypatch.setattr(admin_router, "user_sync_running", lambda: False)
    headers = await _admin_headers(client)

    async with admin_router._user_sync_lock:
        r = await client.post("/admin/users/refresh", headers=headers)

    assert r.status_code == 200
    assert r.json()["status"] == "already_running"
    assert "already in progress" in r.json()["detail"]


@pytest.mark.asyncio
async def test_refresh_reports_running_via_the_worker_flag(client, monkeypatch):
    """A sync started elsewhere (the schedule, the backfill page) also blocks it."""

    async def fake_sync_users(session_factory, **kwargs):  # pragma: no cover - not reached
        raise AssertionError("a concurrent extraction was started")

    monkeypatch.setattr(admin_router, "sync_users", fake_sync_users)
    monkeypatch.setattr(admin_router, "user_sync_running", lambda: True)

    r = await client.post("/admin/users/refresh", headers=await _admin_headers(client))
    assert r.json()["status"] == "already_running"


@pytest.mark.asyncio
async def test_refresh_requires_admin(client):
    r = await client.post("/admin/users/refresh")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_status_reports_counts_for_the_button(client, monkeypatch):
    """The Settings button disables itself off /admin/users/status."""
    monkeypatch.setattr(admin_router, "user_sync_running", lambda: False)
    r = await client.get("/admin/users/status", headers=await _admin_headers(client))
    assert r.status_code == 200
    body = r.json()
    assert body["running"] is False
    assert body["licensed_users"] == 0
    assert body["directory_users"] == 0


@pytest.mark.asyncio
async def test_lock_is_released_when_the_sync_fails(monkeypatch):
    """A failed extraction must not wedge the button permanently."""

    async def boom(session_factory, **kwargs):
        raise RuntimeError("Graph said no")

    monkeypatch.setattr(admin_router, "sync_users", boom)
    await admin_router._run_user_sync()
    assert not admin_router._user_sync_lock.locked()
    # And the lock is immediately re-acquirable.
    await asyncio.wait_for(admin_router._user_sync_lock.acquire(), timeout=1)
    admin_router._user_sync_lock.release()
