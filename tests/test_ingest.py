"""Ingestion engine tests using an in-memory fake Graph client.

Verifies the transforms feed the DB correctly, that upserts are idempotent on
``prompt_id``, that watermarks advance, and that a ``job_runs`` record is
written.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from shared.db import SessionLocal
from shared.models import (
    AppConfig,
    EntraUser,
    IngestState,
    JobRun,
    LicenseCount,
    LicensedUser,
    Prompt,
)
from worker.ingest import run_ingest, sync_users

NOW = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
SKU = "639dec6b-bb19-468b-871c-c5c441c4b0cb"


class FakeGraph:
    """Implements the subset of GraphClient the engine calls."""

    def __init__(self, *, licensed, skus, directory, interactions):
        self._licensed = licensed
        self._skus = skus
        self._directory = directory
        self._interactions = interactions
        self.closed = False

    async def iter_licensed_users(self, sku_ids):
        for u in self._licensed:
            yield u

    async def get_subscribed_skus(self):
        return self._skus

    async def iter_directory_users(self):
        for u in self._directory:
            yield u

    async def iter_enterprise_interactions(self, user_id, since, until, *, page_size=100):
        for raw in self._interactions.get(user_id, []):
            yield raw

    async def aclose(self):
        self.closed = True


def _config() -> AppConfig:
    return AppConfig(
        id=1,
        tenant_id="tenant",
        client_id="client",
        client_secret_encrypted="x",
        copilot_sku_ids=[SKU],
        backfill_days=30,
    )


def _fake_graph() -> FakeGraph:
    licensed = [{"id": "user-1"}, {"id": "user-2"}]
    skus = [
        {
            "skuId": SKU,
            "capabilityStatus": "Enabled",
            "consumedUnits": 2,
            "prepaidUnits": {"enabled": 5, "suspended": 0, "warning": 0, "lockedOut": 0},
        },
        {"skuId": "other-sku", "consumedUnits": 100, "prepaidUnits": {"enabled": 200}},
    ]
    directory = [
        {
            "id": "user-1",
            "userPrincipalName": "alice@contoso.com",
            "mail": "alice@contoso.com",
            "userType": "Member",
            "accountEnabled": True,
            "displayName": "Alice",
            "assignedLicenses": [{"skuId": SKU}],
            "manager": {"id": "mgr-1"},
        },
        {  # excluded: onmicrosoft.com service account
            "id": "svc",
            "userPrincipalName": "svc@contoso.onmicrosoft.com",
            "mail": "svc@contoso.onmicrosoft.com",
            "userType": "Member",
            "accountEnabled": True,
        },
    ]
    interactions = {
        "user-1": [
            {
                "id": "p1",
                "sessionId": "c1",
                "appClass": "IPM.SkypeTeams.Message.Copilot.BizChat",
                "conversationType": "bizchat",
                "createdDateTime": "2026-07-20T10:00:00Z",
                "contexts": [],
            },
            {
                "id": "p2",
                "sessionId": "c1",
                "appClass": "IPM.SkypeTeams.Message.Copilot.M365AdminCenter",
                "conversationType": "bizchat",
                "createdDateTime": "2026-07-20T10:05:00Z",
            },
        ],
        "user-2": [
            {
                "id": "p3",
                "sessionId": "c2",
                "appClass": "WebChat",
                "conversationType": "webchat",
                "createdDateTime": "2026-07-21T08:00:00Z",
                "contexts": [],
            },
        ],
    }
    return FakeGraph(
        licensed=licensed, skus=skus, directory=directory, interactions=interactions
    )


@pytest.mark.asyncio
async def test_run_ingest_populates_tables():
    stats = await run_ingest(SessionLocal, graph=_fake_graph(), config=_config(), now=NOW)

    assert stats["licensed_users"] == 2
    assert stats["license_counts"] == 1  # only the Copilot SKU
    assert stats["prompts"]["prompts"] == 2  # p2 (admin center) dropped
    assert stats["entra_users"] == 1  # svc account excluded

    async with SessionLocal() as s:
        prompts = (await s.execute(select(Prompt))).scalars().all()
        assert {p.prompt_id for p in prompts} == {"p1", "p3"}
        p1 = next(p for p in prompts if p.prompt_id == "p1")
        assert p1.app_name == "Copilot Chat"
        assert p1.chat_type == "Work"
        assert p1.conversation_id == "c1"

        assert (await s.execute(select(func.count()).select_from(LicensedUser))).scalar_one() == 2
        assert (await s.execute(select(func.count()).select_from(LicenseCount))).scalar_one() == 1
        entra = (await s.execute(select(EntraUser))).scalars().all()
        assert len(entra) == 1
        assert entra[0].manager_id == "mgr-1"
        assert entra[0].has_copilot_license is True

        job = (await s.execute(select(JobRun))).scalars().one()
        assert job.status == "success"


@pytest.mark.asyncio
async def test_run_ingest_is_idempotent():
    graph = _fake_graph()
    await run_ingest(SessionLocal, graph=graph, config=_config(), now=NOW)
    await run_ingest(SessionLocal, graph=_fake_graph(), config=_config(), now=NOW)

    async with SessionLocal() as s:
        total = (await s.execute(select(func.count()).select_from(Prompt))).scalar_one()
        assert total == 2  # no duplication on re-run


@pytest.mark.asyncio
async def test_watermark_advances():
    await run_ingest(SessionLocal, graph=_fake_graph(), config=_config(), now=NOW)
    async with SessionLocal() as s:
        states = (await s.execute(select(IngestState))).scalars().all()
        keys = {st.key for st in states}
        assert "prompt:user-1" in keys and "prompt:user-2" in keys
        for st in states:
            assert st.watermark is not None
            assert st.last_status == "ok"


@pytest.mark.asyncio
async def test_sync_users_populates_users_without_prompts():
    # The user-only sync refreshes licensed + directory users (and licence
    # counts) but must NOT pull any prompts.
    stats = await sync_users(SessionLocal, graph=_fake_graph(), config=_config(), now=NOW)

    assert stats["licensed_users"] == 2
    assert stats["license_counts"] == 1
    assert stats["entra_users"] == 1
    assert "prompts" not in stats

    async with SessionLocal() as s:
        assert (
            await s.execute(select(func.count()).select_from(LicensedUser))
        ).scalar_one() == 2
        assert (
            await s.execute(select(func.count()).select_from(EntraUser))
        ).scalar_one() == 1
        # No prompts pulled by a user-only sync.
        assert (
            await s.execute(select(func.count()).select_from(Prompt))
        ).scalar_one() == 0
        job = (
            await s.execute(select(JobRun).where(JobRun.job_name == "users"))
        ).scalars().one()
        assert job.status == "success"
