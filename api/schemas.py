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
    # Build stamp, repeated here because this endpoint is reachable before
    # sign-in. Knowing which build is live is most useful exactly when you
    # cannot get in to look at the About page.
    build_date: str | None = None
    build_time: str | None = None


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


# --- customer branding ---------------------------------------------------
class BrandingOut(BaseModel):
    """Public branding payload (docs/specs/customer-branding.md).

    Reachable before sign-in, like /auth/config, so the sign-in screen can
    brand itself. Carries no uploaded bytes: the logo is fetched from its own
    URL, which keeps this payload small and lets the image be cached and
    revalidated on its own terms.
    """

    org_display_name: str | None = None
    brand_primary_hex: str | None = None
    # Eleven "#rrggbb" stops each, keyed by stop number AS A STRING. JSON
    # object keys are strings, and the TypeScript side indexes them as strings;
    # a numeric key type-checks there and then misses at runtime. Empty when no
    # colour is set, which is the signal to leave the CSS defaults alone.
    ramp_light: dict[str, str] = {}
    ramp_dark: dict[str, str] = {}
    # True when the dark accent was brightened to reach WCAG AA. Surfaced so
    # the admin is told we changed their colour rather than discovering it.
    dark_accent_lifted: bool = False
    dark_accent_contrast: float | None = None
    # White heading text sits on the sign-in gradient. When its lightest stop
    # would fail AA the panel renders one stop deeper instead.
    gradient_needs_deepening: bool = False
    # Write-only-asset idiom, mirroring has_client_secret above: the bytes
    # never come back in JSON, only whether a logo is there and where it is.
    has_logo_light: bool = False
    has_logo_dark: bool = False
    logo_light_url: str | None = None
    logo_dark_url: str | None = None
    logo_light_needs_plate: bool = False


class BrandingIn(BaseModel):
    org_display_name: str | None = Field(default=None, max_length=80)
    brand_primary_hex: str | None = None


class BrandingAdminOut(BrandingOut):
    """Adds what only an admin needs to see."""

    logo_light_bytes: int | None = None
    logo_dark_bytes: int | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None


class RampPreviewIn(BaseModel):
    brand_primary_hex: str


class RampPreviewOut(BaseModel):
    """A derivation with nothing written — powers the live Settings preview."""

    ramp_light: dict[str, str]
    ramp_dark: dict[str, str]
    light_accent_contrast: float
    dark_accent_contrast: float
    dark_accent_lifted: bool
    gradient_needs_deepening: bool


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
