"""Application version metadata, surfaced on the About page.

A CI pipeline can inject BUILD_DATE / BUILD_TIME at image build time; otherwise
the constants below are the released stamp for the current build.
"""
from __future__ import annotations

import os

APP_VERSION = "1.1.0"

# Release/build date (YYYY-MM-DD) and clock time (HH:MM, local build tz).
BUILD_DATE = os.environ.get("BUILD_DATE", "2026-09-14")
BUILD_TIME = os.environ.get("BUILD_TIME", "11:00 AEST")
