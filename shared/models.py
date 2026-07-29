"""SQLAlchemy 2.0 ORM models.

Uses the project's Conversations/Prompts vocabulary — never Graph's
"session"/"interaction". Postgres-specific column types (JSONB, ARRAY) fall back
to portable JSON variants under SQLite so the test-suite can run without a
Postgres instance.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base

# Portable column types: JSONB/ARRAY on Postgres, plain JSON on SQLite (tests).
JsonType = JSONB().with_variant(JSON(), "sqlite")
StrArray = ARRAY(String).with_variant(JSON(), "sqlite")


class Prompt(Base):
    """One row per Copilot prompt (Graph 'interaction')."""

    __tablename__ = "prompts"

    prompt_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, index=True)
    conversation_id: Mapped[str | None] = mapped_column(Text, index=True)
    app_name: Mapped[str | None] = mapped_column(Text)
    prompt_date: Mapped[date | None] = mapped_column(Date, index=True)
    conversation_type: Mapped[str | None] = mapped_column(Text)
    # "App" or "Chat".
    conversation_location: Mapped[str | None] = mapped_column(Text)
    # "Work" | "Web" | "Temporary" | None.
    chat_type: Mapped[str | None] = mapped_column(Text)
    file_location: Mapped[str | None] = mapped_column(Text)
    teams_location: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict | None] = mapped_column(JsonType)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EntraUser(Base):
    """A directory user (filtered to enabled members at ingest time)."""

    __tablename__ = "entra_users"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    upn: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    job_title: Mapped[str | None] = mapped_column(Text)
    company_name: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text)
    office_location: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    manager_id: Mapped[str | None] = mapped_column(Text, index=True)
    account_enabled: Mapped[bool | None] = mapped_column(Boolean)
    user_type: Mapped[str | None] = mapped_column(Text)
    has_copilot_license: Mapped[bool] = mapped_column(Boolean, default=False)
    extension_attribute_1: Mapped[str | None] = mapped_column(Text)
    extension_attribute_2: Mapped[str | None] = mapped_column(Text)
    extension_attribute_3: Mapped[str | None] = mapped_column(Text)
    extension_attribute_4: Mapped[str | None] = mapped_column(Text)
    extension_attribute_5: Mapped[str | None] = mapped_column(Text)
    extension_attribute_6: Mapped[str | None] = mapped_column(Text)
    extension_attribute_7: Mapped[str | None] = mapped_column(Text)
    extension_attribute_8: Mapped[str | None] = mapped_column(Text)
    extension_attribute_9: Mapped[str | None] = mapped_column(Text)
    extension_attribute_10: Mapped[str | None] = mapped_column(Text)
    extension_attribute_11: Mapped[str | None] = mapped_column(Text)
    extension_attribute_12: Mapped[str | None] = mapped_column(Text)
    extension_attribute_13: Mapped[str | None] = mapped_column(Text)
    extension_attribute_14: Mapped[str | None] = mapped_column(Text)
    extension_attribute_15: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LicensedUser(Base):
    """Snapshot of users currently holding a configured Copilot SKU."""

    __tablename__ = "licensed_users"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LicenseCount(Base):
    """Time-series of Copilot license totals (from subscribedSkus)."""

    __tablename__ = "license_counts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recorded_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[int] = mapped_column(Integer, default=0)
    allocated: Mapped[int] = mapped_column(Integer, default=0)
    available: Mapped[int] = mapped_column(Integer, default=0)
    suspended: Mapped[int] = mapped_column(Integer, default=0)
    warning: Mapped[int] = mapped_column(Integer, default=0)
    locked_out: Mapped[int] = mapped_column(Integer, default=0)


class AppConfig(Base):
    """Single-row admin settings. Client secret stored Fernet-encrypted."""

    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    tenant_id: Mapped[str | None] = mapped_column(Text)
    client_id: Mapped[str | None] = mapped_column(Text)
    client_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    copilot_sku_ids: Mapped[list[str]] = mapped_column(
        StrArray, default=["639dec6b-bb19-468b-871c-c5c441c4b0cb"]
    )
    report_access_group_id: Mapped[str | None] = mapped_column(Text)
    backfill_days: Mapped[int] = mapped_column(Integer, default=30)
    schedule_cron: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(Text)


class IngestState(Base):
    """Per-key watermark + last status for incremental ingest/observability."""

    __tablename__ = "ingest_state"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(Text)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[dict | None] = mapped_column(JsonType)


class JobRun(Base):
    """One record per ingestion/backfill run for observability."""

    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(Text, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="running")
    stats: Mapped[dict | None] = mapped_column(JsonType)


class AppUser(Base):
    """Local login account for the password gate."""

    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, default="viewer")  # admin | viewer
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
