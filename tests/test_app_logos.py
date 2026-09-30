"""Every app the demo seeds must resolve to a bundled logo.

Designer was seeded from the first release and never mapped, so it rendered
with a blank spacer where every other app had a mark — visible in a README
screenshot and invisible to any test, because nothing joined the seeder's app
list to the frontend's logo table. This joins them.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEEDER = ROOT / "scripts" / "seed_demo.py"
APP_LABEL = ROOT / "frontend" / "src" / "components" / "AppLabel.tsx"
LOGO_DIR = ROOT / "frontend" / "public" / "logos"


def _seeded_apps() -> list[str]:
    block = re.search(r"_APPS\s*(?::[^=]+)?=\s*\[(.*?)\]", SEEDER.read_text(), re.S)
    assert block, "could not find the seeder's app list"
    apps = re.findall(r'\(\s*"([^"]+)"', block.group(1))
    # Finding the block but parsing nothing out of it is the failure that hides:
    # parametrise over an empty list and pytest collects zero cases, reports
    # green, and checks nothing. Reformat the seeder into a list built by
    # .append() and that is exactly what happens.
    assert apps, "parsed the seeder's app list but found no apps in it"
    return apps


def _logo_map() -> dict[str, str]:
    block = re.search(
        r"const LOGO_FILE: Record<string, string> = \{(.*?)\};",
        APP_LABEL.read_text(),
        re.S,
    )
    assert block, "could not find LOGO_FILE"
    mapping = dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", block.group(1)))
    assert mapping, "found LOGO_FILE but parsed no entries out of it"
    return mapping


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


@pytest.mark.parametrize("app", _seeded_apps())
def test_every_seeded_app_has_a_logo(app: str) -> None:
    file = _logo_map().get(_key(app))
    assert file, f"{app!r} is seeded but has no LOGO_FILE entry"
    assert (LOGO_DIR / f"{file}.png").is_file(), f"{app!r} maps to a missing {file}.png"


def test_every_mapped_logo_file_exists() -> None:
    """A mapping pointing at a file nobody shipped fails the same way silently."""
    missing = sorted(
        {f for f in _logo_map().values() if not (LOGO_DIR / f"{f}.png").is_file()}
    )
    assert not missing, f"LOGO_FILE points at files that do not exist: {missing}"
