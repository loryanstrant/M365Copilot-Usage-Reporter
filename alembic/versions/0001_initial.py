"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompts",
        sa.Column("prompt_id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.Text(), nullable=True),
        sa.Column("app_name", sa.Text(), nullable=True),
        sa.Column("prompt_date", sa.Date(), nullable=True),
        sa.Column("conversation_type", sa.Text(), nullable=True),
        sa.Column("conversation_location", sa.Text(), nullable=True),
        sa.Column("chat_type", sa.Text(), nullable=True),
        sa.Column("file_location", sa.Text(), nullable=True),
        sa.Column("teams_location", sa.Text(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_prompts_user_id", "prompts", ["user_id"])
    op.create_index("ix_prompts_conversation_id", "prompts", ["conversation_id"])
    op.create_index("ix_prompts_prompt_date", "prompts", ["prompt_date"])

    op.create_table(
        "entra_users",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("upn", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("job_title", sa.Text(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("office_location", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("manager_id", sa.Text(), nullable=True),
        sa.Column("account_enabled", sa.Boolean(), nullable=True),
        sa.Column("user_type", sa.Text(), nullable=True),
        sa.Column(
            "has_copilot_license",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        *[
            sa.Column(f"extension_attribute_{i}", sa.Text(), nullable=True)
            for i in range(1, 16)
        ],
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_entra_users_manager_id", "entra_users", ["manager_id"])

    op.create_table(
        "licensed_users",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "license_counts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("recorded_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Integer(), server_default="0", nullable=False),
        sa.Column("allocated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available", sa.Integer(), server_default="0", nullable=False),
        sa.Column("suspended", sa.Integer(), server_default="0", nullable=False),
        sa.Column("warning", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_out", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index("ix_license_counts_recorded_date", "license_counts", ["recorded_date"])

    op.create_table(
        "app_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=True),
        sa.Column("client_id", sa.Text(), nullable=True),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "copilot_sku_ids",
            postgresql.ARRAY(sa.String()),
            server_default="{639dec6b-bb19-468b-871c-c5c441c4b0cb}",
            nullable=False,
        ),
        sa.Column("report_access_group_id", sa.Text(), nullable=True),
        sa.Column("backfill_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column("schedule_cron", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_by", sa.Text(), nullable=True),
    )

    op.create_table(
        "ingest_state",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("watermark", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.Text(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
    )

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_name", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), server_default="running", nullable=False),
        sa.Column("stats", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_job_runs_job_name", "job_runs", ["job_name"])

    op.create_table(
        "app_users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), server_default="viewer", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_app_users_username", "app_users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_table("app_users")
    op.drop_table("job_runs")
    op.drop_table("ingest_state")
    op.drop_table("app_config")
    op.drop_table("license_counts")
    op.drop_table("licensed_users")
    op.drop_table("entra_users")
    op.drop_table("prompts")
