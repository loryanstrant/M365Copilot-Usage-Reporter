"""Switch Copilot licence detection from a SKU list to the service plan.

``copilot_sku_ids`` shipped defaulted to the single Microsoft 365 Copilot SKU,
which meant E7 users — and holders of the second Copilot SKU — were never
counted as licensed. Detection now asks the tenant which of its subscriptions
contain the "Microsoft Copilot with Graph-grounded chat" service plan, so the
field becomes a manual override rather than the source of truth.

An existing row still holds the old default, and leaving it there would keep
overriding detection with exactly the wrong answer. So this clears the field —
but *only* where it still equals the shipped default. A tenant that deliberately
customised the list keeps it, and can clear it in Settings to opt into
detection.

Revision ID: 0007_copilot_sku_autodetect
Revises: 0006_admin_group
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision: str = "0007_copilot_sku_autodetect"
down_revision: str | None = "0006_admin_group"
branch_labels = None
depends_on = None

_LEGACY_DEFAULT = ["639dec6b-bb19-468b-871c-c5c441c4b0cb"]


def _clear_untouched_default(to_value) -> None:
    """Rewrite app_config.copilot_sku_ids only when it is the shipped default.

    Read and compare in Python: the column is a Postgres text[] in production
    but plain JSON on SQLite, so there is no single SQL comparison that works
    on both.
    """
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, copilot_sku_ids FROM app_config")
    ).fetchall()
    for row_id, value in rows:
        current = value
        if isinstance(current, str):
            try:
                current = json.loads(current)
            except ValueError:
                continue
        if list(current or []) != _LEGACY_DEFAULT:
            continue
        bind.execute(
            sa.text("UPDATE app_config SET copilot_sku_ids = :v WHERE id = :i"),
            {"v": to_value, "i": row_id},
        )


def upgrade() -> None:
    bind = op.get_bind()
    empty = [] if bind.dialect.name != "sqlite" else json.dumps([])
    _clear_untouched_default(empty)


def downgrade() -> None:
    """Put the old default back where the list is empty."""
    bind = op.get_bind()
    value = (
        _LEGACY_DEFAULT if bind.dialect.name != "sqlite" else json.dumps(_LEGACY_DEFAULT)
    )
    rows = bind.execute(sa.text("SELECT id, copilot_sku_ids FROM app_config")).fetchall()
    for row_id, current in rows:
        if isinstance(current, str):
            try:
                current = json.loads(current)
            except ValueError:
                continue
        if list(current or []):
            continue
        bind.execute(
            sa.text("UPDATE app_config SET copilot_sku_ids = :v WHERE id = :i"),
            {"v": value, "i": row_id},
        )
