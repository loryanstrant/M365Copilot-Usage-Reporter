"""Entra sign-in (OIDC) behaviour.

Covers the parts we can exercise without talking to Entra: availability
reporting, redirect-URI resolution, the signed state cookie, and the failure
paths. The token exchange itself is MSAL's job and is not re-tested here.
"""
from __future__ import annotations

import json
import time

import httpx
import jwt
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from shared.config import settings
from shared.crypto import encrypt
from shared.db import SessionLocal
from shared.models import AppConfig, AppUser
from shared.security import hash_password


@pytest_asyncio.fixture
async def client():
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        await s.commit()

    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _configure_entra() -> None:
    """Save a plausible app registration, as the Settings page would."""
    async with SessionLocal() as s:
        s.add(
            AppConfig(
                id=1,
                tenant_id="11111111-1111-1111-1111-111111111111",
                client_id="22222222-2222-2222-2222-222222222222",
                client_secret_encrypted=encrypt("not-a-real-secret"),
            )
        )
        await s.commit()


@pytest.mark.asyncio
async def test_config_reports_disabled_until_credentials_saved(client):
    r = await client.get("/auth/config")
    assert r.status_code == 200
    body = r.json()
    assert body["entra_enabled"] is False
    # The redirect URI is offered even when disabled, so Settings can show the
    # value that needs registering in Entra.
    assert body["redirect_uri"].endswith("/auth/oidc/callback")


@pytest.mark.asyncio
async def test_config_reports_enabled_once_configured(client):
    await _configure_entra()
    r = await client.get("/auth/config")
    assert r.json()["entra_enabled"] is True


@pytest.mark.asyncio
async def test_redirect_uri_honours_forwarded_headers(client):
    """Behind a proxy the app must advertise its external address, not its own."""
    r = await client.get(
        "/auth/config",
        headers={"x-forwarded-proto": "https", "x-forwarded-host": "reports.example.com"},
    )
    assert r.json()["redirect_uri"] == "https://reports.example.com/auth/oidc/callback"


@pytest.mark.asyncio
async def test_redirect_uri_prefers_explicit_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://explicit.example.com/")
    r = await client.get(
        "/auth/config",
        headers={"x-forwarded-host": "ignored.example.com"},
    )
    assert r.json()["redirect_uri"] == "https://explicit.example.com/auth/oidc/callback"


@pytest.mark.asyncio
async def test_start_is_unavailable_until_configured(client):
    r = await client.get("/auth/oidc/start")
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_start_redirects_to_entra_and_sets_signed_state(client, monkeypatch):
    await _configure_entra()

    # Stub MSAL: building a real client performs OIDC discovery over the
    # network. What is under test here is our cookie handling, not MSAL.
    class _StubMsal:
        def initiate_auth_code_flow(self, scopes, redirect_uri):
            return {
                "auth_uri": (
                    "https://login.microsoftonline.com/"
                    "11111111-1111-1111-1111-111111111111/oauth2/v2.0/authorize?x=1"
                ),
                "state": "state-value",
                "code_verifier": "verifier-value",
                "nonce": "nonce-value",
                "redirect_uri": redirect_uri,
                "scope": scopes,
            }

    import api.oidc as oidc

    monkeypatch.setattr(oidc, "_msal_app", lambda cfg: _StubMsal())

    r = await client.get("/auth/oidc/start", follow_redirects=False)

    assert r.status_code == 302
    assert r.headers["location"].startswith(
        "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111"
    )

    cookie = r.cookies.get("usage_oidc_flow")
    assert cookie, "the in-flight flow must be persisted for the callback"

    # Stateless by design: the flow rides in a signed cookie so the callback can
    # land on any replica. Verify it really is signed and carries PKCE material.
    payload = jwt.decode(cookie, settings.secret_key, algorithms=["HS256"])
    flow = json.loads(payload["flow"])
    assert flow["code_verifier"] == "verifier-value"
    assert flow["state"] == "state-value"
    assert payload["exp"] > time.time()
    # The bulky authorize URL is not stored, to stay under the 4KB cookie limit.
    assert "auth_uri" not in flow


@pytest.mark.asyncio
async def test_callback_without_state_fails_gracefully(client):
    await _configure_entra()
    r = await client.get("/auth/oidc/callback?code=abc", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/#sso_error=")


@pytest.mark.asyncio
async def test_callback_rejects_tampered_state(client):
    await _configure_entra()
    forged = jwt.encode(
        {"flow": json.dumps({"state": "x"}), "exp": int(time.time()) + 600},
        "the-wrong-signing-key",
        algorithm="HS256",
    )
    r = await client.get(
        "/auth/oidc/callback?code=abc",
        cookies={"usage_oidc_flow": forged},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "sso_error" in r.headers["location"]


@pytest.mark.asyncio
async def test_easy_auth_headers_are_ignored(client):
    """Easy Auth is gone: forged platform headers must not grant access.

    Previously these headers were trusted. Nothing should read them now, so a
    caller presenting them still has no session.
    """
    import base64

    principal = base64.b64encode(
        json.dumps(
            {
                "claims": [
                    {"typ": "oid", "val": "33333333-3333-3333-3333-333333333333"},
                    {"typ": "preferred_username", "val": "attacker@example.com"},
                ]
            }
        ).encode()
    ).decode()

    r = await client.get("/auth/me", headers={"x-ms-client-principal": principal})
    assert r.status_code in (401, 403)


# --------------------------------------------------------------------------- #
# Viewer group gate
#
# Restored from the deleted tests/test_easyauth.py: the gate moved into
# api/oidc.py unchanged, and its fail-closed behaviour is the thing standing
# between "restricted to a security group" and "open to the whole tenant".
# --------------------------------------------------------------------------- #
OID = "11111111-1111-1111-1111-111111111111"
GROUP = "22222222-2222-2222-2222-222222222222"


class _FakeGraph:
    def __init__(self, matched=None, raises=False):
        self.matched = matched or []
        self.raises = raises
        self.calls = []

    async def check_member_groups(self, oid, group_ids):
        self.calls.append((oid, list(group_ids)))
        if self.raises:
            raise RuntimeError("graph unreachable")
        return self.matched

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_group_gate_allows_when_no_group_configured(session):
    import api.oidc as oidc

    oidc.reset_group_cache()
    p = oidc.Principal(object_id=OID, name="a", groups=[])
    assert await oidc.is_group_member(p, "", session) is True


@pytest.mark.asyncio
async def test_group_gate_uses_token_claims_without_calling_graph(session, monkeypatch):
    import api.oidc as oidc

    oidc.reset_group_cache()

    def _boom(cfg):  # pragma: no cover - must never run
        raise AssertionError("Graph must not be called when the claim is present")

    monkeypatch.setattr(oidc, "build_graph_client", _boom)
    p = oidc.Principal(object_id=OID, name="a", groups=[GROUP])
    assert await oidc.is_group_member(p, GROUP, session) is True


@pytest.mark.asyncio
async def test_group_gate_fails_closed_when_unconfigured(session):
    """No credentials stored means membership cannot be proven — so deny."""
    import api.oidc as oidc

    oidc.reset_group_cache()
    p = oidc.Principal(object_id=OID, name="a", groups=[])
    assert await oidc.is_group_member(p, GROUP, session) is False


@pytest.mark.asyncio
async def test_group_gate_allows_confirmed_member(session, monkeypatch):
    import api.oidc as oidc

    oidc.reset_group_cache()
    session.add(
        AppConfig(id=1, tenant_id="t", client_id="c", client_secret_encrypted="enc")
    )
    await session.commit()
    fake = _FakeGraph(matched=[GROUP])
    monkeypatch.setattr(oidc, "build_graph_client", lambda cfg: fake)
    p = oidc.Principal(object_id=OID, name="a", groups=[])
    assert await oidc.is_group_member(p, GROUP, session) is True
    assert fake.calls == [(OID, [GROUP])]


@pytest.mark.asyncio
async def test_group_gate_denies_non_member(session, monkeypatch):
    import api.oidc as oidc

    oidc.reset_group_cache()
    session.add(
        AppConfig(id=1, tenant_id="t", client_id="c", client_secret_encrypted="enc")
    )
    await session.commit()
    monkeypatch.setattr(oidc, "build_graph_client", lambda cfg: _FakeGraph(matched=[]))
    p = oidc.Principal(object_id=OID, name="a", groups=[])
    assert await oidc.is_group_member(p, GROUP, session) is False


@pytest.mark.asyncio
async def test_group_gate_fails_closed_when_graph_errors(session, monkeypatch):
    """A Graph outage must not silently open the dashboard up."""
    import api.oidc as oidc

    oidc.reset_group_cache()
    session.add(
        AppConfig(id=1, tenant_id="t", client_id="c", client_secret_encrypted="enc")
    )
    await session.commit()
    monkeypatch.setattr(oidc, "build_graph_client", lambda cfg: _FakeGraph(raises=True))
    p = oidc.Principal(object_id=OID, name="a", groups=[])
    assert await oidc.is_group_member(p, GROUP, session) is False
