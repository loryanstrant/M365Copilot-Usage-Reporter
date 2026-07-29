"""Password hashing helpers (bcrypt).

Uses the ``bcrypt`` library directly. bcrypt only considers the first 72 bytes
of a password, so inputs are truncated to 72 bytes to avoid runtime errors on
bcrypt >= 4.1 (which raises instead of silently truncating).
"""
from __future__ import annotations

import bcrypt

_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    return password.encode("utf-8")[:_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
