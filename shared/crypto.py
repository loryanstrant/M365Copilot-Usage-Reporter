"""Symmetric encryption for secrets at rest (Graph client secret).

Uses Fernet with a key supplied via the ``FERNET_KEY`` environment variable.
Generate one with:  ``python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"``
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from shared.config import settings


class CryptoError(RuntimeError):
    """Raised when encryption/decryption fails or no key is configured."""


def _fernet() -> Fernet:
    if not settings.fernet_key:
        raise CryptoError(
            "FERNET_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"` and set it in the environment."
        )
    try:
        return Fernet(settings.fernet_key.encode())
    except (ValueError, TypeError) as exc:  # malformed key
        raise CryptoError(f"Invalid FERNET_KEY: {exc}") from exc


def encrypt(plaintext: str) -> str:
    """Encrypt a string, returning a urlsafe token string suitable for DB storage."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt`."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise CryptoError("Could not decrypt value (wrong key or corrupt data).") from exc
