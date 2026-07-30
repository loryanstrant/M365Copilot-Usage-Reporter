"""Tests for the centrally-hostable app-name translations."""
from __future__ import annotations

import pytest

from shared import translations as tr
from worker.transforms import normalise_app_name, transform_interaction


def _raw(app_class: str, **extra) -> dict:
    base = {
        "id": "p1",
        "sessionId": "s1",
        "appClass": f"IPM.SkypeTeams.Message.Copilot.{app_class}",
        "conversationType": "bizchat",
        "createdDateTime": "2026-07-01T09:00:00Z",
    }
    base.update(extra)
    return base


def test_defaults_map_and_exclude():
    d = tr.default_translations()
    assert d.display_name("BizChat") == "Copilot Chat"
    assert d.display_name("Word") == "Word"  # unknown passes through
    assert d.is_excluded("PredictiveChat") is True
    assert d.is_excluded("M365AdminCenter") is True
    assert d.is_excluded("Word") is False


def test_predictivechat_is_dropped_at_transform():
    assert transform_interaction(_raw("PredictiveChat"), "u1") is None


def test_admin_center_still_dropped():
    assert transform_interaction(_raw("M365AdminCenter"), "u1") is None


def test_real_app_kept():
    row = transform_interaction(_raw("Word"), "u1")
    assert row is not None and row["app_name"] == "Word"


def test_merge_overrides_and_adds():
    payload = {
        "app_names": {"newsurface": "New Surface", "word": "Microsoft Word"},
        "excluded_apps": ["somebot"],
    }
    merged = tr._merge(payload)
    # Added mapping + override of a passthrough.
    assert merged.display_name("NewSurface") == "New Surface"
    assert merged.display_name("Word") == "Microsoft Word"
    # Built-in defaults are preserved when the remote doesn't mention them.
    assert merged.display_name("BizChat") == "Copilot Chat"
    # Exclusions are the union of default + remote.
    assert merged.is_excluded("SomeBot") is True
    assert merged.is_excluded("PredictiveChat") is True


def test_merge_ignores_malformed_payload():
    merged = tr._merge({"app_names": "nope", "excluded_apps": 42})
    assert merged.display_name("BizChat") == "Copilot Chat"
    assert merged.is_excluded("PredictiveChat") is True


def test_normalise_app_name_uses_injected_translations():
    merged = tr._merge({"app_names": {"word": "Microsoft Word"}})
    assert normalise_app_name("Word", merged) == "Microsoft Word"
    # Default (no injection) leaves unknown names unchanged.
    assert normalise_app_name("Word") == "Word"


@pytest.mark.asyncio
async def test_load_translations_disabled_url_returns_defaults():
    tr.reset_cache()
    out = await tr.load_translations(url="")
    assert out.display_name("BizChat") == "Copilot Chat"
    tr.reset_cache()
