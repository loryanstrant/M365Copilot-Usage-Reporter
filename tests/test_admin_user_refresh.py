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

from sqlalchemy import select

from api.routers import admin as admin_router
from shared.db import SessionLocal
from shared.models import AppConfig, AppUser, JobRun
from shared.security import hash_password
from worker import ingest


@pytest.fixture(autouse=True)
def _reset_user_sync_progress():
    """``_user_sync`` is a module global; don't let one test's run colour another."""
    ingest._user_sync = type(ingest._user_sync)()
    yield
    ingest._user_sync = type(ingest._user_sync)()


def _config() -> AppConfig:
    """Credentials complete enough that the Graph client is never built."""
    return AppConfig(
        id=1, tenant_id="tenant", client_id="client", client_secret_encrypted="x"
    )


def _stub_sync_steps(monkeypatch, *, licensed: int, directory: int) -> None:
    """Replace the three Graph-reading steps with counts, nothing else."""

    async def _licensed(session, graph, config):
        return licensed

    async def _counts(session, graph, config, now):
        return 1

    async def _directory(session, graph, config):
        return directory

    monkeypatch.setattr(ingest, "sync_licensed_users", _licensed)
    monkeypatch.setattr(ingest, "sync_license_counts", _counts)
    monkeypatch.setattr(ingest, "sync_entra_users", _directory)


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
async def test_failure_is_visible_on_the_status_endpoint(client):
    """The refresh answers "started" even when the sync then fails.

    With no Graph credentials stored, ``sync_users`` raises immediately — and the
    only place that is visible is ``/admin/users/status``, which is what the
    Settings button polls to turn its banner into an error. If this contract
    changes, the UI goes back to claiming success while nothing happened.
    """
    headers = await _admin_headers(client)

    r = await client.post("/admin/users/refresh", headers=headers)
    assert r.json()["status"] == "started"

    body = (await client.get("/admin/users/status", headers=headers)).json()
    assert body["status"] == "failed"
    assert body["detail"] == "Graph is not configured yet."
    assert body["running"] is False
    assert body["updated_at"] is not None


@pytest.mark.asyncio
async def test_a_credential_failure_does_not_jam_the_button_forever(client):
    """The failure that used to wedge the feature for the life of the process.

    A tenant ID saved without a client secret makes ``build_graph_client`` raise
    before any job row exists. That raise used to escape the guarded block with
    ``_user_sync.status`` still "running", so ``user_sync_running()`` answered
    True forever and every later press got ``already_running`` with nothing
    running — unrecoverable short of restarting the container.
    """
    async with SessionLocal() as s:
        s.add(AppConfig(id=1, tenant_id="tenant", client_id="client"))
        await s.commit()
    headers = await _admin_headers(client)

    first = await client.post("/admin/users/refresh", headers=headers)
    assert first.json()["status"] == "started"

    body = (await client.get("/admin/users/status", headers=headers)).json()
    assert body["running"] is False
    assert body["status"] == "failed"
    assert "not fully configured" in body["detail"]

    second = await client.post("/admin/users/refresh", headers=headers)
    assert second.json()["status"] == "started"


@pytest.mark.asyncio
async def test_a_cancelled_sync_does_not_jam_it_either(monkeypatch):
    """CancelledError is a BaseException, so `except Exception` never sees it."""

    async def cancelled(session, graph, config):
        raise asyncio.CancelledError()

    monkeypatch.setattr(ingest, "sync_licensed_users", cancelled)

    with pytest.raises(asyncio.CancelledError):
        await ingest.sync_users(SessionLocal, graph=object(), config=_config())

    assert ingest.user_sync_running() is False
    assert ingest.get_user_sync_progress()["status"] == "failed"

    # And the job row is not left claiming to be running — Scan history and the
    # "last run" line both read it.
    async with SessionLocal() as s:
        rows = (
            await s.execute(select(JobRun).where(JobRun.job_name == "users"))
        ).scalars().all()
        assert [r.status for r in rows] == ["failed"]


@pytest.mark.asyncio
async def test_a_failure_does_not_report_the_previous_runs_counts(monkeypatch):
    """Counts are zeroed at the start, so `failed` never carries stale numbers."""
    _stub_sync_steps(monkeypatch, licensed=7, directory=9)
    await ingest.sync_users(SessionLocal, graph=object(), config=_config())
    assert ingest.get_user_sync_progress()["licensed_users"] == 7
    assert ingest.get_user_sync_progress()["directory_users"] == 9

    async def boom(session, graph, config):
        raise RuntimeError("Graph said no")

    monkeypatch.setattr(ingest, "sync_licensed_users", boom)
    with pytest.raises(RuntimeError):
        await ingest.sync_users(SessionLocal, graph=object(), config=_config())

    progress = ingest.get_user_sync_progress()
    assert progress["status"] == "failed"
    assert progress["licensed_users"] == 0
    assert progress["directory_users"] == 0


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
