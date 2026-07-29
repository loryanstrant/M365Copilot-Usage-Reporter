"""Authentication: JWT issuance and role-based dependencies.

MVP password gate backed by the ``app_users`` table (bcrypt). Tokens are signed
HS256 JWTs carrying the username (``sub``) and role. Two dependencies gate
routes: :func:`get_current_user` (any authenticated user) and
:func:`require_admin` (admin role only).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.db import get_session
from shared.models import AppUser
from shared.security import verify_password

_ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    username: str
    role: str


def create_access_token(username: str, role: str) -> str:
    """Issue a signed JWT for the given user."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": username, "role": role, "exp": expire}
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
    except JWTError as exc:
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
    return CurrentUser(username=username, role=payload.get("role", "viewer"))


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency that requires the ``admin`` role."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required"
        )
    return user


__all__ = [
    "CurrentUser",
    "authenticate_user",
    "create_access_token",
    "get_current_user",
    "get_session",
    "require_admin",
]
