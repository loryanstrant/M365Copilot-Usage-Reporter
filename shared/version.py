"""Application version metadata, surfaced on the About page.

A CI pipeline injects BUILD_DATE / BUILD_TIME at image build time. Local and
development builds leave them unset, and the About page says so.
"""
from __future__ import annotations

import os

APP_VERSION = "1.1.0"


def _stamp(name: str) -> str | None:
    """Return an injected build stamp, or None when nothing injected one.

    There is deliberately no fallback literal here. A hardcoded date drifts the
    moment it is written and then asserts, confidently and wrongly, that the
    running image was built on a day nobody built anything. Admitting we have no
    stamp is the more honest failure, so callers get None and the About page
    renders "development build".
    """
    return os.environ.get(name, "").strip() or None


# Release/build date (YYYY-MM-DD) and clock time (HH:MM, build tz).
BUILD_DATE = _stamp("BUILD_DATE")
BUILD_TIME = _stamp("BUILD_TIME")
