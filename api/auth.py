"""Authentication: JWT issuance and role-based dependencies.

Password gate backed by the ``app_users`` table (bcrypt), plus Entra sign-in
(see :mod:`api.oidc`). Tokens are signed HS256 JWTs carrying the username
(``sub``), the role, and — for Entra sign-ins — the Entra object ID, UPN and
display name so the personal view can filter to the signed-in person and the
UI can greet them by name.

Three dependencies gate routes: :func:`get_current_user` (any authenticated
user), :func:`require_admin` (administrators only) and :func:`require_org_view`
(may see organisation-wide data).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.db import get_session
from shared.models import AppConfig, AppUser
from shared.security import verify_password

_ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    username: str
    role: str
    # Present only for Entra sign-ins. The password admin has no directory
    # identity, so there is no "me" to filter their data down to.
    oid: str | None = None
    upn: str | None = None
    # The Entra ``name`` claim. Absent for the password admin, and absent from
    # tokens issued before display names were carried — callers must cope with
    # None rather than assume it is set.
    display_name: str | None = None

    @property
    def has_personal_view(self) -> bool:
        return bool(self.oid or self.upn)


def create_access_token(
    username: str,
    role: str,
    *,
    oid: str | None = None,
    upn: str | None = None,
    display_name: str | None = None,
) -> str:
    """Issue a signed JWT for the given user."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload: dict[str, object] = {"sub": username, "role": role, "exp": expire}
    if oid:
        payload["oid"] = oid
    if upn:
        payload["upn"] = upn
    if display_name:
        payload["name"] = display_name
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


async def authenticate_user(
    session: AsyncSession, username: str, password: str
) -> AppUser | None:
    """Return the user when credentials are valid, else ``None``."""
    user = await session.scalar(
        select(AppUser).where(AppUser.username == username)
    )
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """Resolve and validate the bearer token into a :class:`CurrentUser`."""
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            creds.credentials, settings.secret_key, algorithms=[_ALGORITHM]
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    return CurrentUser(
        username=username,
        role=payload.get("role", "viewer"),
        oid=payload.get("oid"),
        upn=payload.get("upn"),
        display_name=payload.get("name"),
    )


async def is_admin(user: CurrentUser, session: AsyncSession) -> bool:
    """Whether this user administers the app.

    True for the local password account whose ``app_users`` row carries the
    admin role, and for members of the configured Entra admin group.

    Membership is evaluated per request rather than baked into the token, for
    the same reason :func:`can_view_org` does it: the group check is already
    cached for a few minutes, whereas a token lives for hours. Removing
    someone from the group should bite in minutes, not at next sign-in.

    Note the asymmetry with :func:`can_view_org`: an unset admin group grants
    admin to *nobody*. Administration has always been an explicit grant, so an
    empty field must fail closed rather than hand the keys to everyone who can
    sign in.
    """
    if user.role == "admin":
        return True

    cfg = await session.get(AppConfig, 1)
    group_id = (cfg.admin_group_id if cfg else None) or ""
    if not group_id or not user.oid:
        return False

    from api.oidc import Principal, is_group_member

    principal = Principal(object_id=user.oid, name=user.username, groups=[])
    return await is_group_member(principal, group_id, session)


async def personal_view_user_id(
    user: CurrentUser, session: AsyncSession
) -> str | None:
    """The directory user whose personal view this account may see, if any.

    Normally that is the signed-in person, from the token's Entra object ID.
    The exception is the local password account while demo data is loaded: it
    has no directory identity of its own, so it stands in for the seeded demo
    persona. Without that, the personal pages cannot be opened at all without
    Entra, and anyone evaluating the product never sees the pages the README
    advertises.

    Resolved per request rather than baked into the token on purpose. A token
    lives for hours, so minting the persona into it would leave someone looking
    at a fictional person's activity for the rest of the day after they cleared
    the demo data.

    Only the administrator stands in. The binding exists so whoever loaded the
    demo data can see what it unlocks, not so that every local account in the
    deployment inherits a fictional identity.
    """
    if user.oid:
        return user.oid
    if user.role != "admin":
        return None
    cfg = await session.get(AppConfig, 1)
    return (cfg.demo_persona_user_id if cfg else None) or None


async def effective_role(user: CurrentUser, session: AsyncSession) -> str:
    """The role the UI should act on, after the admin group is considered.

    The token's own role claim is not enough: an Entra sign-in is always issued
    as a viewer, and admin is decided per request from group membership.
    """
    return "admin" if await is_admin(user, session) else user.role


async def require_admin(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """Dependency that requires administrator rights."""
    if not await is_admin(user, session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required"
        )
    return user


async def can_view_org(user: CurrentUser, session: AsyncSession) -> bool:
    """Whether this user may see organisation-wide data.

    Admins always may. For everyone else, membership of the configured
    organisation-view group decides it.

    Membership is evaluated per request rather than baked into the token on
    purpose: the group check is already cached for a few minutes, whereas a
    token lives for hours. Revoking someone's access should bite in minutes,
    not at next sign-in.

    When no group is configured the org view is open to every signed-in user.
    That is deliberate — before this feature existed, anyone who could sign in
    saw everything, so an unset field must not silently lock people out on
    upgrade.
    """
    if await is_admin(user, session):
        return True

    cfg = await session.get(AppConfig, 1)
    group_id = (cfg.org_view_group_id if cfg else None) or ""
    if not group_id:
        return True
    if not user.oid:
        return False

    from api.oidc import Principal, is_group_member

    principal = Principal(object_id=user.oid, name=user.username, groups=[])
    return await is_group_member(principal, group_id, session)


async def require_org_view(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """Dependency for organisation-wide endpoints."""
    if not await can_view_org(user, session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Organisation-wide reporting is limited to an approved group. "
                "Ask your administrator if you need access."
            ),
        )
    return user


__all__ = [
    "CurrentUser",
    "authenticate_user",
    "can_view_org",
    "create_access_token",
    "effective_role",
    "get_current_user",
    "get_session",
    "is_admin",
    "personal_view_user_id",
    "require_admin",
    "require_org_view",
]
