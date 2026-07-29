"""Unit tests for the deterministic ingest transforms.

These pin the Power Query rules that were ported into
:mod:`worker.transforms` so future refactors can't silently change the numbers.
"""
from __future__ import annotations

from datetime import date

import pytest

from worker.transforms import (
    derive_chat_type,
    derive_conversation_location,
    derive_file_location,
    derive_teams_location,
    extract_locations,
    is_included_entra_user,
    normalise_app_name,
    strip_app_prefix,
    transform_entra_user,
    transform_interaction,
    transform_subscribed_sku,
)


# --- strip_app_prefix ----------------------------------------------------
def test_strip_app_prefix_removes_known_prefix():
    assert strip_app_prefix("IPM.SkypeTeams.Message.Copilot.BizChat") == "BizChat"


def test_strip_app_prefix_leaves_others_untouched():
    assert strip_app_prefix("Word") == "Word"
    assert strip_app_prefix(None) is None


# --- normalise_app_name --------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("BizChat", "Copilot Chat"),
        ("WebChat", "Copilot Chat"),
        ("PrivateChat", "Copilot Chat"),
        ("VivaEngage", "Viva Engage"),
        ("OfficeCopilotSearchAnswer", "Copilot Search"),
        ("Word", "Word"),  # unknown passes through
    ],
)
def test_normalise_app_name(raw, expected):
    assert normalise_app_name(raw) == expected


# --- derive_conversation_location ---------------------------------------
def test_conversation_location_app_vs_chat():
    assert derive_conversation_location("appchat") == "App"
    assert derive_conversation_location("AppChat") == "App"
    assert derive_conversation_location("bizchat") == "Chat"
    assert derive_conversation_location(None) == "Chat"


# --- derive_chat_type ----------------------------------------------------
@pytest.mark.parametrize(
    "conversation_type,app_class,expected",
    [
        ("bizchat", "BizChat", "Work"),
        ("webchat", "WebChat", "Web"),
        (None, "PrivateChat", "Temporary"),
        ("appchat", "Word", None),
        (None, None, None),
    ],
)
def test_derive_chat_type(conversation_type, app_class, expected):
    assert derive_chat_type(conversation_type, app_class) == expected


# --- derive_teams_location -----------------------------------------------
def test_teams_location_strips_prefix():
    assert derive_teams_location("TeamsChat") == "Chat"
    assert derive_teams_location("TeamsChannel") == "Channel"
    assert derive_teams_location("TeamsMeeting") == "Meeting"
    assert derive_teams_location("pptx") is None  # a file context, not Teams
    assert derive_teams_location(None) is None


# --- derive_file_location ------------------------------------------------
def test_file_location_classifies_host():
    assert (
        derive_file_location(
            "https://contoso-my.sharepoint.com/personal/x/Doc.aspx"
        )
        == "OneDrive"
    )
    assert (
        derive_file_location("https://contoso.sharepoint.com/sites/x/Doc.aspx")
        == "SharePoint"
    )
    assert derive_file_location("https://whiteboard.cloud.microsoft/me/x") is None
    assert derive_file_location(None) is None


# --- extract_locations ---------------------------------------------------
def test_extract_locations_file_context():
    contexts = [
        {
            "contextType": "docx",
            "displayName": "report.docx",
            "contextReference": "https://contoso.sharepoint.com/sites/x/report.docx",
        }
    ]
    file_location, teams_location = extract_locations(contexts)
    assert file_location == "SharePoint"
    assert teams_location is None


def test_extract_locations_teams_context():
    contexts = [{"contextType": "TeamsChannel", "displayName": "General"}]
    file_location, teams_location = extract_locations(contexts)
    assert file_location is None
    assert teams_location == "Channel"


def test_extract_locations_empty():
    assert extract_locations(None) == (None, None)
    assert extract_locations([]) == (None, None)


# --- transform_interaction ----------------------------------------------
def test_transform_interaction_full_row():
    raw = {
        "id": "prompt-1",
        "sessionId": "conv-1",
        "appClass": "IPM.SkypeTeams.Message.Copilot.BizChat",
        "conversationType": "bizchat",
        "createdDateTime": "2026-07-01T09:30:00Z",
        "contexts": [
            {"contextType": "FileLocation", "contextReference": "/f/a.docx"},
        ],
    }
    row = transform_interaction(raw, user_id="user-1")
    assert row is not None
    assert row["prompt_id"] == "prompt-1"
    assert row["conversation_id"] == "conv-1"
    assert row["user_id"] == "user-1"
    assert row["app_name"] == "Copilot Chat"
    assert row["prompt_date"] == date(2026, 7, 1)
    assert row["conversation_location"] == "Chat"
    assert row["chat_type"] == "Work"
    assert row["file_location"] is None  # "/f/a.docx" is not a sharepoint URL
    assert row["raw_json"] is raw


def test_transform_interaction_drops_admin_center():
    raw = {
        "id": "p2",
        "sessionId": "s2",
        "appClass": "IPM.SkypeTeams.Message.Copilot.M365AdminCenter",
        "conversationType": "bizchat",
        "createdDateTime": "2026-07-01T00:00:00Z",
    }
    assert transform_interaction(raw, user_id="u") is None


# --- is_included_entra_user ---------------------------------------------
def _member(**overrides):
    base = {
        "id": "u1",
        "userPrincipalName": "alice@contoso.com",
        "mail": "alice@contoso.com",
        "userType": "Member",
        "accountEnabled": True,
    }
    base.update(overrides)
    return base


def test_included_user_happy_path():
    assert is_included_entra_user(_member()) is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"userType": "Guest"},
        {"accountEnabled": False},
        {"mail": ""},
        {"mail": None},
        {"mail": "svc@contoso.onmicrosoft.com"},
        {"userPrincipalName": "svc@contoso.onmicrosoft.com", "mail": "svc@contoso.onmicrosoft.com"},
    ],
)
def test_excluded_users(overrides):
    assert is_included_entra_user(_member(**overrides)) is False


# --- transform_entra_user -----------------------------------------------
def test_transform_entra_user_maps_fields_and_extensions():
    user = _member(
        displayName="Alice A",
        jobTitle="Engineer",
        department="R&D",
        manager={"id": "mgr-1"},
        onPremisesExtensionAttributes={"extensionAttribute1": "cost-centre-42"},
    )
    row = transform_entra_user(user, has_copilot_license=True)
    assert row["user_id"] == "u1"
    assert row["display_name"] == "Alice A"
    assert row["manager_id"] == "mgr-1"
    assert row["has_copilot_license"] is True
    assert row["extension_attribute_1"] == "cost-centre-42"
    assert row["extension_attribute_15"] is None


# --- transform_subscribed_sku -------------------------------------------
def test_transform_subscribed_sku_computes_available():
    sku = {
        "capabilityStatus": "Enabled",
        "consumedUnits": 80,
        "prepaidUnits": {"enabled": 100, "suspended": 1, "warning": 2, "lockedOut": 0},
    }
    row = transform_subscribed_sku(sku, recorded_date=date(2026, 7, 29))
    assert row["enabled"] == 100
    assert row["allocated"] == 80
    assert row["available"] == 20
    assert row["suspended"] == 1
    assert row["warning"] == 2
    assert row["status"] == "Enabled"
