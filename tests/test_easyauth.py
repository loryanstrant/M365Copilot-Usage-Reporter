"""Tests for Entra SSO via Container Apps Easy Auth.

Covers header parsing (base64 principal + fallback headers), the group
membership gate (token claims, Graph fallback, fail-closed), and the
``/auth/mode`` + ``/auth/entra`` endpoints.
"""
from __future__ import annotations

import base64
import json

import httpx
import pytest
from asgi_lifespan import LifespanManager
from starlette.requests import Request

import api.easyauth as easyauth
from api.easyauth import EasyAuthPrincipal, is_group_member, parse_principal, reset_group_cache
from api.main import app
from shared.models import AppConfig

OID = "11111111-1111-1111-1111-111111111111"
GROUP = "22222222-2222-2222-2222-222222222222"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _principal_header(
    *, oid: str = OID, name: str = "alice@contoso.com", groups: list[str] | None = None
) -> str:
    claims = [
        {"typ": "http://schemas.microsoft.com/identity/claims/objectidentifier", "val": oid},
        {"typ": "preferred_username", "val": name},
    ]
    for g in groups or []:
        claims.append({"typ": "groups", "val": g})
    payload = {"auth_typ": "aad", "claims": claims}
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def _make_request(headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw})


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


class _FakeGraph:
    """Stand-in GraphClient whose membership answer is scripted."""

    def __init__(self, matched: list[str]):
        self._matched = matched
        self.calls: list[tuple[str, list[str]]] = []

    async def check_member_groups(self, user_id: str, group_ids: list[str]) -> list[str]:
        self.calls.append((user_id, group_ids))
        return [g for g in group_ids if g in self._matched]

    async def aclose(self) -> None:  # pragma: no cover - trivial
        pass


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_group_cache()
    yield
    reset_group_cache()


# --------------------------------------------------------------------------- #
# parse_principal
# --------------------------------------------------------------------------- #
def test_parse_principal_from_base64_claims():
    req = _make_request({"x-ms-client-principal": _principal_header(groups=[GROUP])})
    p = parse_principal(req)
    assert p is not None
    assert p.object_id == OID
    assert p.name == "alice@contoso.com"
    assert p.groups == [GROUP]


def test_parse_principal_fallback_headers():
    # No base64 blob — fall back to the simple id/name headers.
    req = _make_request(
        {
            "x-ms-client-principal-id": OID,
            "x-ms-client-principal-name": "bob@contoso.com",
        }
    )
    p = parse_principal(req)
    assert p is not None
    assert p.object_id == OID
    assert p.name == "bob@contoso.com"
    assert p.groups == []


def test_parse_principal_absent_returns_none():
    assert parse_principal(_make_request({})) is None


def test_parse_principal_malformed_base64_uses_fallback():
    req = _make_request(
        {
            "x-ms-client-principal": "!!!not-base64!!!",
            "x-ms-client-principal-id": OID,
            "x-ms-client-principal-name": "carol@contoso.com",
        }
    )
    p = parse_principal(req)
    assert p is not None and p.name == "carol@contoso.com"


# --------------------------------------------------------------------------- #
# is_group_member
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_group_member_empty_group_allows(session):
    p = EasyAuthPrincipal(object_id=OID, name="a", groups=[])
    assert await is_group_member(p, "", session) is True


@pytest.mark.asyncio
async def test_group_member_via_claims_no_graph(session, monkeypatch):
    # Membership present in the token claims -> must NOT touch Graph.
    def _boom(cfg):  # pragma: no cover - should never be called
        raise AssertionError("Graph should not be called when claim present")

    monkeypatch.setattr(easyauth, "build_graph_client", _boom)
    p = EasyAuthPrincipal(object_id=OID, name="a", groups=[GROUP])
    assert await is_group_member(p, GROUP, session) is True


@pytest.mark.asyncio
async def test_group_member_fail_closed_when_unconfigured(session):
    # No app credentials stored -> cannot verify -> deny.
    p = EasyAuthPrincipal(object_id=OID, name="a", groups=[])
    assert await is_group_member(p, GROUP, session) is False


@pytest.mark.asyncio
async def test_group_member_via_graph_true(session, monkeypatch):
    session.add(
        AppConfig(id=1, tenant_id="t", client_id="c", client_secret_encrypted="enc")
    )
    await session.commit()
    fake = _FakeGraph(matched=[GROUP])
    monkeypatch.setattr(easyauth, "build_graph_client", lambda cfg: fake)
    p = EasyAuthPrincipal(object_id=OID, name="a", groups=[])
    assert await is_group_member(p, GROUP, session) is True
    assert fake.calls == [(OID, [GROUP])]


@pytest.mark.asyncio
async def test_group_member_via_graph_false(session, monkeypatch):
    session.add(
        AppConfig(id=1, tenant_id="t", client_id="c", client_secret_encrypted="enc")
    )
    await session.commit()
    fake = _FakeGraph(matched=[])
    monkeypatch.setattr(easyauth, "build_graph_client", lambda cfg: fake)
    p = EasyAuthPrincipal(object_id=OID, name="a", groups=[])
    assert await is_group_member(p, GROUP, session) is False


@pytest.mark.asyncio
async def test_group_member_graph_error_fail_closed(session, monkeypatch):
    session.add(
        AppConfig(id=1, tenant_id="t", client_id="c", client_secret_encrypted="enc")
    )
    await session.commit()

    def _raise(cfg):
        raise RuntimeError("graph down")

    monkeypatch.setattr(easyauth, "build_graph_client", _raise)
    p = EasyAuthPrincipal(object_id=OID, name="a", groups=[])
    assert await is_group_member(p, GROUP, session) is False


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_auth_mode_reflects_header(session):
    async with LifespanManager(app), _client() as client:
        off = await client.get("/auth/mode")
        assert off.json() == {"entra_available": False}

        on = await client.get(
            "/auth/mode", headers={"x-ms-client-principal": _principal_header()}
        )
        assert on.json() == {"entra_available": True}


@pytest.mark.asyncio
async def test_entra_login_no_identity_401(session):
    async with LifespanManager(app), _client() as client:
        resp = await client.post("/auth/entra")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_entra_login_no_group_configured_mints_viewer(session):
    async with LifespanManager(app), _client() as client:
        resp = await client.post(
            "/auth/entra",
            headers={"x-ms-client-principal": _principal_header(name="dana@contoso.com")},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["role"] == "viewer"
        assert body["username"] == "dana@contoso.com"

        # The minted JWT is a normal app token and works on /auth/me.
        me = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
        )
        assert me.json() == {"username": "dana@contoso.com", "role": "viewer"}


@pytest.mark.asyncio
async def test_entra_login_group_member_via_claims(session):
    session.add(AppConfig(id=1, report_access_group_id=GROUP))
    await session.commit()
    async with LifespanManager(app), _client() as client:
        resp = await client.post(
            "/auth/entra",
            headers={"x-ms-client-principal": _principal_header(groups=[GROUP])},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == "viewer"


@pytest.mark.asyncio
async def test_entra_login_non_member_forbidden(session, monkeypatch):
    session.add(
        AppConfig(
            id=1,
            tenant_id="t",
            client_id="c",
            client_secret_encrypted="enc",
            report_access_group_id=GROUP,
        )
    )
    await session.commit()
    monkeypatch.setattr(easyauth, "build_graph_client", lambda cfg: _FakeGraph(matched=[]))
    async with LifespanManager(app), _client() as client:
        resp = await client.post(
            "/auth/entra",
            headers={"x-ms-client-principal": _principal_header()},
        )
        assert resp.status_code == 403
