"""Pydantic request/response schemas for the API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# --- auth ---------------------------------------------------------------
class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class UserOut(BaseModel):
    username: str
    role: str
    # Entra's display name. None for the password admin and for tokens issued
    # before display names were carried, so the UI falls back to the username.
    display_name: str | None = None
    # The signed-in person's UPN. Usually the same as username for an Entra
    # sign-in, but not when the password admin is borrowing a demo identity —
    # there the account is "admin" and the person on screen is someone else.
    upn: str | None = None
    # Whether this user may see organisation-wide data. Drives whether the SPA
    # offers the org view or shows it locked.
    can_view_org: bool = True
    # Whether there is an Entra identity to filter a personal view down to.
    # False for the password admin, who therefore lands on the org view.
    has_personal_view: bool = False


class AuthConfigOut(BaseModel):
    entra_enabled: bool
    redirect_uri: str


# --- admin config -------------------------------------------------------
class AppConfigIn(BaseModel):
    tenant_id: str | None = None
    client_id: str | None = None
    # Write-only: only applied when a non-empty value is supplied.
    client_secret: str | None = None
    copilot_sku_ids: list[str] | None = None
    report_access_group_id: str | None = None
    org_view_group_id: str | None = None
    admin_group_id: str | None = None
    backfill_days: int | None = Field(default=None, ge=1, le=3650)
    schedule_cron: str | None = None
    # Friendly recurring-ingest cadence: run every N hours (1..24; 24 = daily).
    schedule_interval_hours: int | None = Field(default=None, ge=1, le=24)


class AppConfigOut(BaseModel):
    tenant_id: str | None = None
    client_id: str | None = None
    has_client_secret: bool = False
    copilot_sku_ids: list[str] = []
    report_access_group_id: str | None = None
    org_view_group_id: str | None = None
    admin_group_id: str | None = None
    backfill_days: int = 30
    schedule_cron: str | None = None
    schedule_interval_hours: int = 24
    configured: bool = False
    updated_at: datetime | None = None
    updated_by: str | None = None


class CopilotSkuOut(BaseModel):
    """A tenant subscription, and whether it grants Copilot."""

    sku_id: str
    name: str
    grants_copilot: bool
    seats: int = 0
    assigned: int = 0


class DirectoryUserOut(BaseModel):
    """One row of the tenant users listing."""

    user_id: str
    user_principal_name: str | None = None
    display_name: str | None = None
    job_title: str | None = None
    department: str | None = None
    company_name: str | None = None
    office_location: str | None = None
    country: str | None = None
    manager_name: str | None = None
    user_type: str | None = None
    has_copilot_license: bool = False
    prompts: int = 0


class TestConnectionOut(BaseModel):
    ok: bool
    token_acquired: bool = False
    subscribed_skus: bool = False
    directory_read: bool = False
    copilot_licensed_users: int | None = None
    # Every subscription found, counted ones first. Drives the Settings panel
    # that shows which SKUs grant Copilot.
    copilot_skus: list[CopilotSkuOut] = []
    detail: str | None = None


class IngestRunOut(BaseModel):
    status: str
    detail: str


# --- status -------------------------------------------------------------
class JobRunOut(BaseModel):
    id: int
    job_name: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stats: dict[str, Any] | None = None


class StatusOut(BaseModel):
    configured: bool
    last_run: JobRunOut | None = None
    prompts: int = 0
    conversations: int = 0
    licensed_users: int = 0
    entra_users: int = 0
