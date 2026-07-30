"""App-name translations, with a centrally-hostable override.

Every Graph ``appClass`` is mapped to a friendly display name, and some app
classes are dropped entirely (system-generated, not genuine human usage). These
rules are baked in as defaults so the app always works offline, but they can
also be **maintained centrally**: deployed instances periodically fetch a JSON
file (``TRANSLATIONS_URL``, default = this project's repo) and merge it OVER the
built-in defaults. That lets renames, new surfaces, and new exclusions roll out
to every deployment without a redeploy.

The fetch is best-effort: any failure (network, bad JSON, timeout) falls back to
the last good value, then to the built-in defaults. It never breaks ingest.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

from shared.config import settings

logger = logging.getLogger("shared.translations")

# Built-in defaults (fallback). Keys are prefix-stripped appClass values,
# lowercased. Keep in sync with translations/app-names.json in the repo.
DEFAULT_APP_NAMES: dict[str, str] = {
    "bizchat": "Copilot Chat",
    "webchat": "Copilot Chat",
    "privatechat": "Copilot Chat",
    "vivaengage": "Viva Engage",
    "officecopilotsearchanswer": "Copilot Search",
}

# App classes that must never appear in the dataset (system-generated or not a
# genuine record of human usage). ``predictivechat`` is a system-generated chat
# type, not a real surface; ``m365admincenter`` was never real usage.
DEFAULT_EXCLUDED_APPS: set[str] = {"m365admincenter", "predictivechat"}


@dataclass(frozen=True)
class Translations:
    """Resolved app-name map + exclusion set used by the ingest transforms."""

    app_names: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_APP_NAMES))
    excluded_apps: frozenset[str] = field(
        default_factory=lambda: frozenset(DEFAULT_EXCLUDED_APPS)
    )

    def is_excluded(self, app_class: str | None) -> bool:
        return bool(app_class) and app_class.strip().lower() in self.excluded_apps

    def display_name(self, app_class: str | None) -> str | None:
        if app_class is None:
            return None
        return self.app_names.get(app_class.strip().lower(), app_class)


def default_translations() -> Translations:
    """The built-in translations (no network)."""
    return Translations()


def _merge(payload: dict) -> Translations:
    """Merge a fetched payload over the built-in defaults (defaults win only
    for keys the remote omits)."""
    app_names = dict(DEFAULT_APP_NAMES)
    raw_names = payload.get("app_names")
    if isinstance(raw_names, dict):
        for k, v in raw_names.items():
            if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                app_names[k.strip().lower()] = v

    excluded = set(DEFAULT_EXCLUDED_APPS)
    raw_excluded = payload.get("excluded_apps")
    if isinstance(raw_excluded, list):
        for item in raw_excluded:
            if isinstance(item, str) and item.strip():
                excluded.add(item.strip().lower())

    return Translations(app_names=app_names, excluded_apps=frozenset(excluded))


# Simple TTL cache so frequent ingest runs don't hammer the remote.
_cache: dict[str, object] = {"value": None, "fetched_at": 0.0}


async def load_translations(
    *,
    url: str | None = None,
    refresh_seconds: int | None = None,
    timeout: float = 10.0,
    force: bool = False,
) -> Translations:
    """Return merged translations, fetching the remote file when the cache is
    stale. Falls back to the last good value, then to built-in defaults.
    """
    resolved_url = url if url is not None else settings.translations_url
    ttl = (
        refresh_seconds
        if refresh_seconds is not None
        else settings.translations_refresh_hours * 3600
    )

    if not resolved_url:
        return default_translations()

    now = time.monotonic()
    cached = _cache["value"]
    if (
        not force
        and cached is not None
        and (now - float(_cache["fetched_at"])) < ttl
    ):
        return cached  # type: ignore[return-value]

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(resolved_url)
            resp.raise_for_status()
            merged = _merge(resp.json())
        _cache["value"] = merged
        _cache["fetched_at"] = now
        logger.info(
            "Loaded translations from %s (%d names, %d exclusions)",
            resolved_url,
            len(merged.app_names),
            len(merged.excluded_apps),
        )
        return merged
    except Exception as exc:  # network, JSON, HTTP — never fatal
        if cached is not None:
            logger.warning("Translations refresh failed (%s); using cached copy", exc)
            return cached  # type: ignore[return-value]
        logger.warning("Translations fetch failed (%s); using built-in defaults", exc)
        return default_translations()


def reset_cache() -> None:
    """Clear the TTL cache (used by tests)."""
    _cache["value"] = None
    _cache["fetched_at"] = 0.0
