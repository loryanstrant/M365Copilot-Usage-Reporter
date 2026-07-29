"""Pytest configuration and shared fixtures.

Tests run against a file-based SQLite database (via aiosqlite) so the suite
needs no Postgres. Environment must be configured *before* importing any app
module, because ``shared.db`` builds its engine at import time.
"""
from __future__ import annotations

import os
import tempfile

# --- Configure environment before importing app modules ------------------
# Force an isolated SQLite database so the suite never touches a real Postgres
# (compose sets DATABASE_URL in the container; a plain setdefault wouldn't win).
_TMP_DB = os.path.join(tempfile.gettempdir(), "copilot_test.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB}"
os.environ["RUN_MIGRATIONS_ON_STARTUP"] = "false"
os.environ["APP_ENV"] = "test"
# Disable first-run admin seeding during tests (tests create their own users).
os.environ["ADMIN_USERNAME"] = ""
os.environ["ADMIN_PASSWORD"] = ""

from cryptography.fernet import Fernet  # noqa: E402

os.environ["FERNET_KEY"] = Fernet.generate_key().decode()

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from shared.db import Base, engine  # noqa: E402
import shared.models  # noqa: F401,E402  (register tables)


@pytest_asyncio.fixture(autouse=True)
async def _create_schema():
    """Create all tables before each test and drop them afterwards."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def session():
    from shared.db import SessionLocal

    async with SessionLocal() as s:
        yield s
