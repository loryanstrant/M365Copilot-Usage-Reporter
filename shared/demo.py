"""The demo persona: a seeded identity the password admin can borrow.

Signing in with ADMIN_USERNAME/ADMIN_PASSWORD gives you no Entra identity, and
the personal view is derived entirely from the token's object ID. So anyone
evaluating the app with demo data — which is exactly what the deploy guide
tells them to do — could read about the personal pages in the README and never
reach them.

Seeding records one of the generated people here; the login route hands that
identity to the password admin, so the personal view works without Entra.
Clearing demo data removes the binding, and there is never a row in a
deployment that has not been seeded, so a live sign-in is untouched.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import IngestState

# Namespaced like the ingest watermarks that share this table.
DEMO_PERSONA_KEY = "demo:persona"


async def demo_persona(session: AsyncSession) -> dict[str, str] | None:
    """The seeded identity to sign the password admin in as, if there is one."""
    row = await session.get(IngestState, DEMO_PERSONA_KEY)
    if row is None or not row.detail:
        return None
    detail = row.detail
    if not detail.get("user_id"):
        return None
    return {
        "user_id": str(detail["user_id"]),
        "upn": str(detail.get("upn") or ""),
        "display_name": str(detail.get("display_name") or ""),
    }


__all__ = ["DEMO_PERSONA_KEY", "demo_persona"]
