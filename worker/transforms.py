"""Pure, deterministic ingest-time transforms.

Maps Microsoft Graph vocabulary onto this project's vocabulary at ingest time:
a Graph **session** becomes a **Conversation** (``conversation_id``) and a Graph
**interaction** becomes a **Prompt** (``prompt_id``). Nothing downstream of this
module ever sees "session" or "interaction".

Every function here is a pure function of its inputs (no I/O, no clock, no
globals) so the rules can be pinned down with small JSON fixtures in the tests.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# Prefix stamped onto Copilot app identifiers by Graph; stripped at ingest.
APP_PREFIX = "IPM.SkypeTeams.Message.Copilot."

# App identifier that must never appear in the dataset.
EXCLUDED_APP = "M365AdminCenter"

# Normalisation of the raw (prefix-stripped) app identifier to a display name.
_APP_NAME_MAP = {
    "bizchat": "Copilot Chat",
    "webchat": "Copilot Chat",
    "privatechat": "Copilot Chat",
    "vivaengage": "Viva Engage",
    "officecopilotsearchanswer": "Copilot Search",
}

# Fragment (case-insensitive) in a UPN/mail that marks a non-primary account.
_ONMICROSOFT = "onmicrosoft.com"


def strip_app_prefix(value: str | None) -> str | None:
    """Remove the ``IPM.SkypeTeams.Message.Copilot.`` prefix if present."""
    if value is None:
        return None
    if value.startswith(APP_PREFIX):
        return value[len(APP_PREFIX):]
    return value


def normalise_app_name(app_class: str | None) -> str | None:
    """Map a prefix-stripped app identifier to its friendly display name.

    Unknown identifiers are returned unchanged.
    """
    if app_class is None:
        return None
    return _APP_NAME_MAP.get(app_class.strip().lower(), app_class)


def derive_conversation_location(conversation_type: str | None) -> str:
    """"App" when the conversation type contains "appchat", else "Chat"."""
    if conversation_type and "appchat" in conversation_type.lower():
        return "App"
    return "Chat"


def derive_chat_type(
    conversation_type: str | None, app_class: str | None
) -> str | None:
    """Bucket the prompt as Work / Web / Temporary, or ``None``.

    - ``bizchat`` (conversation type or app) -> "Work"
    - ``webchat`` (conversation type or app) -> "Web"
    - ``PrivateChat`` (app) -> "Temporary"
    """
    ct = (conversation_type or "").lower()
    ac = (app_class or "").lower()
    if "bizchat" in ct or ac == "bizchat":
        return "Work"
    if "webchat" in ct or ac == "webchat":
        return "Web"
    if ac == "privatechat":
        return "Temporary"
    return None


def derive_file_location(context_reference: str | None) -> str | None:
    """Classify a file context's URL as OneDrive or SharePoint.

    Mirrors the original Power Automate flow: a ``-my.sharepoint.com`` host is a
    personal OneDrive; any other ``sharepoint.com`` host is SharePoint; anything
    else (e.g. a Whiteboard/Loop URL) is not a document location.
    """
    if not context_reference:
        return None
    ref = context_reference.lower()
    if "-my.sharepoint.com" in ref:
        return "OneDrive"
    if "sharepoint.com" in ref:
        return "SharePoint"
    return None


def derive_teams_location(context_type: str | None) -> str | None:
    """Classify a Teams context as Chat / Channel / Meeting.

    Mirrors the flow (keep contextType only when it contains "Team") plus the
    Power BI step that strips the "Teams" prefix (e.g. ``TeamsChannel`` ->
    ``Channel``). The result is title-cased for a clean label.
    """
    if not context_type or "team" not in context_type.lower():
        return None
    lowered = context_type.lower()
    idx = lowered.find("teams")
    after = context_type[idx + len("teams"):] if idx != -1 else context_type
    after = after.strip(" /\\:>-\t")
    return after.capitalize() if after else None


def extract_locations(
    contexts: list[dict[str, Any]] | None,
) -> tuple[str | None, str | None]:
    """Pull ``(file_location, teams_location)`` from an interaction's contexts.

    Follows the original solution, which inspects only the first context: a file
    context carries a document URL in ``contextReference`` (classified to
    OneDrive/SharePoint), while a Teams context carries a ``contextType`` such as
    ``TeamsChat`` (classified to Chat/Channel/Meeting).
    """
    if not contexts:
        return None, None
    first = contexts[0] or {}
    file_location = derive_file_location(first.get("contextReference"))
    teams_location = derive_teams_location(first.get("contextType"))
    return file_location, teams_location


def _parse_date(value: str | None) -> date | None:
    """Parse an ISO-8601 timestamp to a ``date`` (tolerating a trailing Z)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def transform_interaction(
    raw: dict[str, Any], user_id: str
) -> dict[str, Any] | None:
    """Turn a raw Graph interaction into a **Prompt** row, or ``None`` to drop.

    Returns ``None`` for rows that must be excluded (e.g. M365 Admin Center).
    """
    app_class = strip_app_prefix(raw.get("appClass"))
    if app_class == EXCLUDED_APP:
        return None

    conversation_type = raw.get("conversationType")
    file_location, teams_location = extract_locations(raw.get("contexts"))

    return {
        "prompt_id": raw.get("id"),
        "user_id": user_id,
        "conversation_id": raw.get("sessionId"),
        "app_name": normalise_app_name(app_class),
        "prompt_date": _parse_date(raw.get("createdDateTime")),
        "conversation_type": conversation_type,
        "conversation_location": derive_conversation_location(conversation_type),
        "chat_type": derive_chat_type(conversation_type, app_class),
        "file_location": file_location,
        "teams_location": teams_location,
        "raw_json": raw,
    }


def has_configured_sku(user: dict[str, Any], sku_ids: list[str]) -> bool:
    """True when the user holds any of the configured Copilot SKUs."""
    wanted = set(sku_ids)
    assigned = {
        lic.get("skuId") for lic in (user.get("assignedLicenses") or [])
    }
    return bool(wanted & assigned)


def is_included_entra_user(user: dict[str, Any]) -> bool:
    """Apply the directory-user inclusion filter used at ingest.

    Keep only enabled members with a real mailbox that is not an
    ``onmicrosoft.com`` account.
    """
    if (user.get("userType") or "").lower() != "member":
        return False
    if user.get("accountEnabled") is not True:
        return False
    mail = (user.get("mail") or "").strip()
    if not mail:
        return False
    upn = user.get("userPrincipalName") or ""
    if _ONMICROSOFT in mail.lower() or _ONMICROSOFT in upn.lower():
        return False
    return True


def transform_entra_user(
    user: dict[str, Any], *, has_copilot_license: bool = False
) -> dict[str, Any]:
    """Map a raw Graph user onto the ``entra_users`` column set."""
    ext = user.get("onPremisesExtensionAttributes") or {}
    row: dict[str, Any] = {
        "user_id": user.get("id"),
        "upn": user.get("userPrincipalName"),
        "email": user.get("mail"),
        "display_name": user.get("displayName"),
        "job_title": user.get("jobTitle"),
        "company_name": user.get("companyName"),
        "department": user.get("department"),
        "office_location": user.get("officeLocation"),
        "country": user.get("country"),
        "manager_id": (user.get("manager") or {}).get("id"),
        "account_enabled": user.get("accountEnabled"),
        "user_type": user.get("userType"),
        "has_copilot_license": has_copilot_license,
    }
    for i in range(1, 16):
        row[f"extension_attribute_{i}"] = ext.get(f"extensionAttribute{i}")
    return row


def transform_subscribed_sku(
    sku: dict[str, Any], recorded_date: date
) -> dict[str, Any]:
    """Map a ``subscribedSku`` entry to a ``license_counts`` row.

    ``available`` is derived as ``enabled - allocated`` (never negative).
    """
    prepaid = sku.get("prepaidUnits") or {}
    enabled = int(prepaid.get("enabled") or 0)
    allocated = int(sku.get("consumedUnits") or 0)
    return {
        "recorded_date": recorded_date,
        "status": sku.get("capabilityStatus"),
        "enabled": enabled,
        "allocated": allocated,
        "available": max(enabled - allocated, 0),
        "suspended": int(prepaid.get("suspended") or 0),
        "warning": int(prepaid.get("warning") or 0),
        "locked_out": int(prepaid.get("lockedOut") or 0),
    }
