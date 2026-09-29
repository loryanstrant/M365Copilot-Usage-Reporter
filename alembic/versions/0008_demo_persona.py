"""Add app_config.demo_persona_user_id.

Loading demo data binds the local admin account to one of the seeded directory
users, and this is where that binding lives. Without it the personal pages
cannot be reached at all without an Entra sign-in — ``has_personal_view`` needs
a directory identity and the password admin has none — so anyone evaluating the
product with demo data never sees the pages the README advertises.

NULL on upgrade, and set only by an explicit demo seed. It is cleared when demo
data is cleared and dropped once a real collection succeeds, so a deployment
that never seeds is untouched.

Replaces an earlier attempt that kept this in an ``ingest_state`` row. That
table is a set of ingest watermarks; an identity binding squatting in it was
invisible from the models and would have puzzled whoever read it next. The
sibling solutions store it here, and all four now agree.

Revision ID: 0008_demo_persona
Revises: 0007_copilot_sku_autodetect
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008_demo_persona"
down_revision: str | None = "0007_copilot_sku_autodetect"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_config", sa.Column("demo_persona_user_id", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("app_config", "demo_persona_user_id")
