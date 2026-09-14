"""Entra ID single sign-on, performed by the app itself.

The app is its own OpenID Connect client: it runs the authorization-code flow
with PKCE against Entra directly, rather than relying on a hosting platform to
authenticate in front of it. That means sign-in behaves identically on Azure
Container Apps, Docker on a NAS, Kubernetes, or anywhere else the container
runs — there is no dependency on Azure "Easy Auth".

It reuses the app registration already stored in ``app_config`` for Graph
ingest, so an operator configures one set of credentials, not two. The only
extra setup is registering the redirect URI, which the Settings page displays.

MSAL performs the security-critical validation (PKCE, ``state``, ``nonce``,
issuer, audience and signature) inside ``acquire_token_by_auth_code_flow`` — we
deliberately do not hand-roll any of it.

Optionally checks membership of a configured Entra security group (via app-only
Graph ``checkMemberGroups``). SSO users are viewers; administration stays behind
the password gate.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import jwt
import msal
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from shared.config import settings
from shared.crypto import decrypt
from shared.models import AppConfig
from worker.ingest import build_graph_client

logger = logging.getLogger("api.oidc")

# Cookie carrying the in-flight MSAL flow between /start and /callback.
# Browsers ignore port numbers when scoping cookies, so this name is unique to
# this solution to avoid clashing with sibling apps on the same localhost.
STATE_COOKIE = "usage_oidc_flow"
# Generous enough for a slow sign-in (MFA prompts), short enough to bound replay.
STATE_TTL_SECONDS = 600

CALLBACK_PATH = "/auth/oidc/callback"

# Claim names that carry the user's object id / display name.
_OID_CLAIMS = ("oid", "http://schemas.microsoft.com/identity/claims/objectidentifier")
_NAME_CLAIMS = ("preferred_username", "upn", "email", "name")

# Cache group-membership decisions briefly so we don't call Graph per request.
_GROUP_TTL_SECONDS = 300
_group_cache: dict[tuple[str, str], tuple[float, bool]] = {}

# Cached MSAL clients, keyed by (tenant_id, client_id) -> (secret, client).
# Building one costs a network round trip for OIDC discovery.
_app_cache: dict[tuple[str, str], tuple[str, "msal.ConfidentialClientApplication"]] = {}


@dataclass
class Principal:
    """A signed-in Entra user, normalised away from token-format details."""

    object_id: str
    name: str
    groups: list[str] = field(default_factory=list)


class OidcNotConfigured(RuntimeError):
    """Raised when Entra sign-in is attempted before credentials are saved."""


def is_configured(cfg: AppConfig | None) -> bool:
    """True when ``app_config`` holds enough to run the sign-in flow."""
    return bool(
        cfg is not None
        and cfg.tenant_id
        and cfg.client_id
        and cfg.client_secret_encrypted
    )


def public_base_url(request: Request) -> str:
    """Best-effort external origin of this deployment, without trailing slash.

    Explicit configuration wins, because behind a reverse proxy the app cannot
    reliably infer its own public address. Falling back to forwarded headers
    covers Container Apps ingress and most proxies; ``request.base_url`` covers
    running it directly.
    """
    configured = (settings.public_base_url or "").strip()
    if configured:
        return configured.rstrip("/")

    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        # A proxy chain may append multiple values; the first is the origin.
        host = forwarded_host.split(",")[0].strip()
        proto = (request.headers.get("x-forwarded-proto") or "https").split(",")[0].strip()
        return f"{proto}://{host}".rstrip("/")

    return str(request.base_url).rstrip("/")


def redirect_uri(request: Request) -> str:
    """The exact value that must be registered on the Entra app registration."""
    return f"{public_base_url(request)}{CALLBACK_PATH}"


def _msal_app(cfg: AppConfig) -> msal.ConfidentialClientApplication:
    """Return a cached MSAL client for this app registration.

    Constructing one performs OIDC discovery against Entra over the network, so
    they are cached and reused: otherwise every sign-in would pay for a fresh
    round trip. MSAL client objects are safe to share.
    """
    if not is_configured(cfg):
        raise OidcNotConfigured("Entra credentials are not fully configured.")

    secret = decrypt(cfg.client_secret_encrypted)
    key = (cfg.tenant_id, cfg.client_id)
    cached = _app_cache.get(key)
    if cached and cached[0] == secret:
        return cached[1]

    app = msal.ConfidentialClientApplication(
        client_id=cfg.client_id,
        client_credential=secret,
        authority=f"https://login.microsoftonline.com/{cfg.tenant_id}",
    )
    _app_cache[key] = (secret, app)
    return app


def reset_app_cache() -> None:
    """Drop cached MSAL clients, e.g. after credentials are changed."""
    _app_cache.clear()


async def begin_flow(cfg: AppConfig, request: Request) -> tuple[str, str]:
    """Start sign-in.

    Returns ``(authorize_url, state_cookie_value)``. MSAL generates the PKCE
    verifier, ``state`` and ``nonce``; we persist its flow dict in a signed
    cookie so the callback can complete on *any* replica.

    MSAL is synchronous and talks to the network, so it runs in a worker thread
    rather than blocking the event loop.
    """
    uri = redirect_uri(request)

    def _start() -> dict[str, Any]:
        app = _msal_app(cfg)
        # No Graph scopes: this flow only establishes who the user is. Group
        # checks use the existing app-only credentials, so no delegated consent
        # is required.
        return app.initiate_auth_code_flow(scopes=[], redirect_uri=uri)

    flow = await run_in_threadpool(_start)
    auth_uri = flow.get("auth_uri")
    if not auth_uri:
        raise OidcNotConfigured("Entra did not return an authorization URL.")

    # auth_uri is long and not needed to redeem the code; dropping it keeps the
    # cookie comfortably under the 4KB browser limit.
    stored = {k: v for k, v in flow.items() if k != "auth_uri"}
    cookie = jwt.encode(
        {"flow": json.dumps(stored), "exp": int(time.time()) + STATE_TTL_SECONDS},
        settings.secret_key,
        algorithm="HS256",
    )
    return auth_uri, cookie


async def complete_flow(
    cfg: AppConfig, cookie_value: str, params: dict[str, Any]
) -> Principal:
    """Redeem the authorization code and return the signed-in principal.

    Raises ``ValueError`` when the handshake fails for any reason — expired
    state, tampered response, user cancellation, or a rejected code.
    """
    try:
        payload = jwt.decode(cookie_value, settings.secret_key, algorithms=["HS256"])
        flow = json.loads(payload["flow"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise ValueError("Sign-in session expired or was tampered with.") from exc

    def _redeem() -> dict[str, Any]:
        app = _msal_app(cfg)
        # Validates state, nonce, PKCE, issuer, audience and signature.
        return app.acquire_token_by_auth_code_flow(flow, params)

    try:
        result = await run_in_threadpool(_redeem)
    except ValueError as exc:
        # MSAL raises on a mismatched state rather than returning an error dict.
        raise ValueError(f"Sign-in could not be completed: {exc}") from exc

    if "error" in result:
        detail = result.get("error_description") or result["error"]
        raise ValueError(f"Entra rejected the sign-in: {detail}")

    claims = result.get("id_token_claims") or {}
    oid = next((claims[c] for c in _OID_CLAIMS if claims.get(c)), None)
    name = next((claims[c] for c in _NAME_CLAIMS if claims.get(c)), None)
    if not oid or not name:
        raise ValueError("Entra did not return an identifiable user.")

    groups = claims.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]
    return Principal(object_id=str(oid), name=str(name), groups=[str(g) for g in groups])


async def is_group_member(
    principal: Principal, group_id: str, session: AsyncSession
) -> bool:
    """True when the principal belongs to ``group_id``.

    Prefers group claims already present in the token; otherwise asks Graph
    (app-only) and caches the answer briefly. Fails closed (returns False) if
    Graph is unreachable/unconfigured, so access is never granted by accident.
    """
    if not group_id:
        return True
    if group_id in principal.groups:
        return True

    key = (principal.object_id, group_id)
    hit = _group_cache.get(key)
    now = time.monotonic()
    if hit and (now - hit[0]) < _GROUP_TTL_SECONDS:
        return hit[1]

    cfg = await session.get(AppConfig, 1)
    if not is_configured(cfg):
        return False  # can't verify -> deny
    allowed = False
    try:
        client = build_graph_client(cfg)
        try:
            matched = await client.check_member_groups(principal.object_id, [group_id])
            allowed = group_id in matched
        finally:
            await client.aclose()
    except Exception as exc:  # network / Graph — fail closed
        logger.warning("Group membership check failed for %s: %s", principal.name, exc)
        allowed = False

    _group_cache[key] = (now, allowed)
    return allowed


def reset_group_cache() -> None:
    _group_cache.clear()
