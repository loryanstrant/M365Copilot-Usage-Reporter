"""Tests for secret-at-rest encryption and one-touch-friendly key coercion."""
from __future__ import annotations

from cryptography.fernet import Fernet

from shared import crypto


def test_valid_fernet_key_is_used_verbatim():
    key = Fernet.generate_key().decode()
    assert crypto.coerce_fernet_key(key) == key.encode()


def test_arbitrary_string_derives_a_valid_key():
    # A GUID-like value (what an ARM template would auto-generate) is not a valid
    # Fernet key on its own, but must still yield a usable one.
    derived = crypto.coerce_fernet_key("3f2504e0-4f89-41d3-9a0c-0305e82c3301")
    # Must construct a working Fernet without raising.
    f = Fernet(derived)
    token = f.encrypt(b"hello")
    assert f.decrypt(token) == b"hello"


def test_derivation_is_deterministic():
    a = crypto.coerce_fernet_key("some-random-seed")
    b = crypto.coerce_fernet_key("some-random-seed")
    assert a == b
    assert crypto.coerce_fernet_key("other-seed") != a


def test_encrypt_decrypt_round_trip(monkeypatch):
    # Point the module at a derived key and confirm a full round-trip.
    monkeypatch.setattr(crypto.settings, "fernet_key", "not-a-real-fernet-key")
    secret = "super-secret-graph-client-secret"
    token = crypto.encrypt(secret)
    assert token != secret
    assert crypto.decrypt(token) == secret
