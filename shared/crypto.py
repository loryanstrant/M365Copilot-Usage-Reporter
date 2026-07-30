"""Symmetric encryption for secrets at rest (Graph client secret).

Uses Fernet with a key supplied via the ``FERNET_KEY`` environment variable.
A proper Fernet key is urlsafe-base64 of 32 bytes; generate one with
``python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"``.

To support one-touch deployments (where an ARM template auto-generates a random
value like a GUID), any non-empty ``FERNET_KEY`` is accepted: a value that is
already a valid Fernet key is used verbatim, otherwise a stable key is derived
from it (SHA-256 → urlsafe-base64). Derivation is deterministic, so the same
input always yields the same key and previously encrypted data stays readable.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from shared.config import settings


class CryptoError(RuntimeError):
    """Raised when encryption/decryption fails or no key is configured."""


def coerce_fernet_key(raw: str) -> bytes:
    """Return a valid Fernet key (bytes) for an arbitrary secret string.

    A value that already parses as a Fernet key is returned unchanged (so
    existing deployments keep working); anything else is hashed into a valid
    32-byte urlsafe-base64 key.
    """
    encoded = raw.encode()
    try:
        Fernet(encoded)  # validates the urlsafe-base64 32-byte format
        return encoded
    except (ValueError, TypeError):
        digest = hashlib.sha256(encoded).digest()  # exactly 32 bytes
        return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    if not settings.fernet_key:
        raise CryptoError(
            "FERNET_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"` and set it in the environment."
        )
    return Fernet(coerce_fernet_key(settings.fernet_key))


def encrypt(plaintext: str) -> str:
    """Encrypt a string, returning a urlsafe token string suitable for DB storage."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt`."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise CryptoError("Could not decrypt value (wrong key or corrupt data).") from exc
