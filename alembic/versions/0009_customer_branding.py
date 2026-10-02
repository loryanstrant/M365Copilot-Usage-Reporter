"""Add customer branding: an organisation name, a brand colour, and logos.

A customer self-hosting this app has no way to make it read as their tool. This
adds the storage behind that: two columns on ``app_config`` for the name and
the single seed colour, plus a ``branding_asset`` table holding the uploaded
logo bytes.

The logos get their own table rather than two more ``app_config`` columns on
purpose. ``app_config`` is read with ``session.get(AppConfig, 1)`` on nearly
every request, including the unauthenticated ``GET /auth/config`` that every
page load hits before sign-in, and ``session.get()`` selects every column. Two
1 MB images there would widen the hottest read in the application to 2 MB for
the sake of data almost no request wants. Postgres would TOAST the values out
of line, but SQLAlchemy would still fetch them.

Only the seed colour is stored, never the derived ramps: they are computed on
read by ``shared.branding``, so there is exactly one place a colour decision
lives and no possibility of a stored ramp disagreeing with the algorithm that
would produce it today.

NULL and empty on upgrade. An install that never sets branding is unaffected,
and the application renders exactly as it did before.

Revision ID: 0009_customer_branding
Revises: 0008_demo_persona
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0009_customer_branding"
down_revision: str | None = "0008_demo_persona"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_config", sa.Column("org_display_name", sa.Text(), nullable=True))
    op.add_column("app_config", sa.Column("brand_primary_hex", sa.Text(), nullable=True))

    op.create_table(
        "branding_asset",
        # "light" | "dark" — one row each at most, so the variant is the key.
        sa.Column("variant", sa.Text(), primary_key=True),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        # sha256 prefix: doubles as the ETag and the ?v= cache-buster.
        sa.Column("etag", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "needs_light_plate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_by", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("branding_asset")
    op.drop_column("app_config", "brand_primary_hex")
    op.drop_column("app_config", "org_display_name")
