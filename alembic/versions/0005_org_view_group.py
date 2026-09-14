"""Add app_config.org_view_group_id.

Membership of this Entra group unlocks the organisation-wide view. It is
deliberately separate from ``report_access_group_id``, which governs whether
someone can open the report at all — repurposing that one would have handed a
personal view to people a tenant had explicitly excluded.

Left NULL on upgrade, which means "org view open to everyone who can sign in".
That matches the behaviour before the personal view existed, so upgrading does
not silently lock anyone out.

Revision ID: 0005_org_view_group
Revises: 0004_purge_predictivechat
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005_org_view_group"
down_revision: str | None = "0004_purge_predictivechat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_config", sa.Column("org_view_group_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("app_config", "org_view_group_id")
