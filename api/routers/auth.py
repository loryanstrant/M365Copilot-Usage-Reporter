"""Authentication routes: password login, current user, and Entra sign-in.

Entra sign-in is run by the app itself (see ``api.oidc``), so it works on any
host rather than only on Azure. The password gate remains the first-run and
break-glass route. Administration is reachable either through it or, when an
admin group is configured, by an Entra sign-in from a member of that group.
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import (
    CurrentUser,
    authenticate_user,
    can_view_org,
    create_access_token,
    effective_role,
    get_current_user,
    personal_view_user_id,
)
from api.oidc import (
    STATE_COOKIE,
    STATE_TTL_SECONDS,
    OidcNotConfigured,
    begin_flow,
    complete_flow,
    is_configured,
    is_group_member,
    redirect_uri,
)
from api.schemas import AuthConfigOut, LoginIn, TokenOut, UserOut
from shared.db import get_session
from shared.version import BUILD_DATE, BUILD_TIME
from shared.models import AppConfig, EntraUser

logger = logging.getLogger("api.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# Cookie is scoped to the sign-in endpoints so it is never sent with API calls.
_COOKIE_PATH = "/auth/oidc"


def _is_https(request: Request) -> bool:
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    return (forwarded or request.url.scheme) == "https"


@router.post("/login", response_model=TokenOut)
async def login(
    body: LoginIn, session: AsyncSession = Depends(get_session)
) -> TokenOut:
    user = await authenticate_user(session, body.username, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    # The demo persona is deliberately NOT minted into the token. It is resolved
    # per request instead (see api.auth.personal_view_user_id), so clearing demo
    # data takes effect at once rather than whenever this token happens to expire.
    token = create_access_token(user.username, user.role)
    return TokenOut(access_token=token, username=user.username, role=user.role)


@router.get("/config", response_model=AuthConfigOut)
async def auth_config(
    request: Request, session: AsyncSession = Depends(get_session)
) -> AuthConfigOut:
    """Tell the SPA whether Entra sign-in is available, and show the redirect URI.

    The redirect URI is returned even when sign-in is not yet configured, so the
    Settings page can display the exact value to register in Entra.
    """
    cfg = await session.get(AppConfig, 1)
    return AuthConfigOut(
        entra_enabled=is_configured(cfg),
        redirect_uri=redirect_uri(request),
        build_date=BUILD_DATE,
        build_time=BUILD_TIME,
    )


@router.get("/oidc/start")
async def oidc_start(
    request: Request, session: AsyncSession = Depends(get_session)
) -> RedirectResponse:
    """Redirect the browser to Entra to sign in."""
    cfg = await session.get(AppConfig, 1)
    try:
        auth_uri, state = await begin_flow(cfg, request)
    except OidcNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    response = RedirectResponse(auth_uri, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=_is_https(request),
        # Lax (not Strict) so the cookie survives the top-level redirect back
        # from Entra; the flow is a GET navigation, so Lax is sufficient.
        samesite="lax",
        path=_COOKIE_PATH,
    )
    return response


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request, session: AsyncSession = Depends(get_session)
) -> RedirectResponse:
    """Complete sign-in and hand the app's own token back to the SPA.

    The token travels in the URL fragment: fragments are never sent to a server,
    so it cannot leak into access logs or a Referer header. The SPA stores it and
    strips it from the address bar immediately.
    """
    cfg = await session.get(AppConfig, 1)
    cookie = request.cookies.get(STATE_COOKIE, "")

    def _fail(message: str) -> RedirectResponse:
        logger.info("Entra sign-in failed: %s", message)
        resp = RedirectResponse(
            f"/#sso_error={quote(message)}", status_code=status.HTTP_302_FOUND
        )
        resp.delete_cookie(STATE_COOKIE, path=_COOKIE_PATH)
        return resp

    if not cookie:
        return _fail("Sign-in session expired. Please try again.")

    try:
        principal = await complete_flow(cfg, cookie, dict(request.query_params))
    except (OidcNotConfigured, ValueError) as exc:
        return _fail(str(exc))

    group_id = (cfg.report_access_group_id if cfg else None) or ""
    if group_id and not await is_group_member(principal, group_id, session):
        return _fail("You are not a member of the group allowed to view this report.")

    # Entra sign-ins are always minted as viewers. Administrator rights are
    # decided per request from the admin group (see api.auth.is_admin), so the
    # role in the token is a floor, never the final word.
    token = create_access_token(
        principal.name,
        "viewer",
        oid=principal.object_id,
        upn=principal.name,
        display_name=principal.display_name,
    )
    response = RedirectResponse(f"/#sso={token}", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(STATE_COOKIE, path=_COOKIE_PATH)
    return response


@router.get("/me", response_model=UserOut)
async def me(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    me_id = await personal_view_user_id(user, session)
    display_name, upn = user.display_name, user.upn
    # An admin standing in for a demo persona is, as far as the personal pages
    # are concerned, that person — so name them rather than the account. Only
    # reached when a demo seed set the binding.
    if me_id and not user.oid:
        profile = await session.get(EntraUser, me_id)
        if profile is not None:
            display_name = profile.display_name or display_name
            upn = profile.upn or upn
    return UserOut(
        username=user.username,
        role=await effective_role(user, session),
        display_name=display_name,
        upn=upn,
        can_view_org=await can_view_org(user, session),
        has_personal_view=me_id is not None,
    )
