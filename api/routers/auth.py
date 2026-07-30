"""Authentication routes: login, current-user, and Entra SSO."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import (
    CurrentUser,
    authenticate_user,
    create_access_token,
    get_current_user,
)
from api.easyauth import is_group_member, parse_principal
from api.schemas import AuthModeOut, LoginIn, TokenOut, UserOut
from shared.db import get_session
from shared.models import AppConfig

router = APIRouter(prefix="/auth", tags=["auth"])


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
    token = create_access_token(user.username, user.role)
    return TokenOut(access_token=token, username=user.username, role=user.role)


@router.get("/mode", response_model=AuthModeOut)
async def auth_mode(request: Request) -> AuthModeOut:
    """Tell the SPA whether an Entra SSO identity is present (so it can attempt a
    silent sign-in) — true only when Easy Auth injected a principal header."""
    return AuthModeOut(entra_available=parse_principal(request) is not None)


@router.post("/entra", response_model=TokenOut)
async def entra_login(
    request: Request, session: AsyncSession = Depends(get_session)
) -> TokenOut:
    """Exchange an Easy Auth (Entra) identity for the app's JWT.

    The identity is injected by the platform and cannot be forged. If a report
    access group is configured, membership is enforced here. SSO users get the
    ``viewer`` role; administration stays behind the password gate.
    """
    principal = parse_principal(request)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No Entra identity present. Sign in via your organisation.",
        )
    cfg = await session.get(AppConfig, 1)
    group_id = (cfg.report_access_group_id if cfg else None) or ""
    if group_id and not await is_group_member(principal, group_id, session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of the group allowed to view this report.",
        )
    token = create_access_token(principal.name, "viewer")
    return TokenOut(access_token=token, username=principal.name, role="viewer")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser = Depends(get_current_user)) -> UserOut:
    return UserOut(username=user.username, role=user.role)
