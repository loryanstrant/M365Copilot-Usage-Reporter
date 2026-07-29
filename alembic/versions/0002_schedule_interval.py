"""add schedule_interval_hours to app_config

Revision ID: 0002_schedule_interval
Revises: 0001_initial
Create Date: 2026-07-30
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_schedule_interval"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_config",
        sa.Column(
            "schedule_interval_hours",
            sa.Integer(),
            nullable=False,
            server_default="24",
        ),
    )


def downgrade() -> None:
    op.drop_column("app_config", "schedule_interval_hours")
