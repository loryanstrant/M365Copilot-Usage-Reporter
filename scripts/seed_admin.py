"""Create the first admin login account.

Usage:
    python scripts/seed_admin.py <username> [password]

If password is omitted you'll be prompted (hidden input). Idempotent: updates
the password/role if the user already exists.
"""
from __future__ import annotations

import asyncio
import getpass
import sys

from sqlalchemy import select

from shared.db import SessionLocal
from shared.migrate import upgrade_to_head
from shared.models import AppUser
from shared.security import hash_password


async def seed(username: str, password: str) -> None:
    upgrade_to_head()
    async with SessionLocal() as session:
        existing = await session.scalar(
            select(AppUser).where(AppUser.username == username)
        )
        if existing:
            existing.password_hash = hash_password(password)
            existing.role = "admin"
            print(f"Updated existing user '{username}' as admin.")
        else:
            session.add(
                AppUser(
                    username=username,
                    password_hash=hash_password(password),
                    role="admin",
                )
            )
            print(f"Created admin user '{username}'.")
        await session.commit()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/seed_admin.py <username> [password]")
        raise SystemExit(1)
    username = sys.argv[1]
    password = sys.argv[2] if len(sys.argv) > 2 else getpass.getpass("Admin password: ")
    if not password:
        print("Password cannot be empty.")
        raise SystemExit(1)
    asyncio.run(seed(username, password))


if __name__ == "__main__":
    main()
