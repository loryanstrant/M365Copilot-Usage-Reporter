"""An install with no branding set must look exactly as it did before.

The brand palette moved from hard-coded hexes in ``tailwind.config.js`` to CSS
custom properties so a customer colour can override it at runtime. These are
static-file assertions (the technique ``tests/test_app_logos.py`` already uses
to join frontend source to backend facts) that the move changed nothing.

Two of them guard a failure mode that a smoke test sails straight past. The
variables must hold space-separated sRGB channels, because Tailwind substitutes
``<alpha-value>`` into ``rgb(...)``. Put a hex there and it emits
``rgb(#2f5ae0 / 1)`` — invalid CSS, which browsers drop *entirely*. On
``.btn-primary`` the ``text-white`` alongside it survives, so the result is a
white-on-white invisible button rather than an obviously wrong colour.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from shared.branding import DEFAULT_RAMP_HEX, STOPS

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
INDEX_CSS = FRONTEND / "src" / "index.css"
TAILWIND_CONFIG = FRONTEND / "tailwind.config.js"

CHANNEL_TRIPLE = re.compile(r"^\d{1,3} \d{1,3} \d{1,3}$")


def _block(css: str, selector: str) -> str:
    """Return the body of the first ``selector { ... }`` block."""
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match, f"no {selector} block found in index.css"
    return match.group(1)


def _vars(body: str) -> dict[int, str]:
    return {
        int(stop): value.strip()
        for stop, value in re.findall(r"--brand-(\d+):\s*([^;]+);", body)
    }


@pytest.fixture(scope="module")
def css() -> str:
    return INDEX_CSS.read_text(encoding="utf-8")


@pytest.mark.parametrize("selector", [":root", ".dark"])
def test_every_stop_is_defined_for_both_modes(css: str, selector: str) -> None:
    found = _vars(_block(css, selector))
    # Assert non-empty first: a regex that matches the block but parses nothing
    # would otherwise make the comparison below vacuously true.
    assert found, f"{selector} defines no --brand-* variables at all"
    assert set(found) == set(STOPS)


@pytest.mark.parametrize("selector", [":root", ".dark"])
def test_defaults_match_the_shipped_hexes(css: str, selector: str) -> None:
    """The byte-for-byte guarantee. Change a default stop and this fails."""
    found = _vars(_block(css, selector))
    assert found
    for stop in STOPS:
        want = DEFAULT_RAMP_HEX[stop]
        r, g, b = (int(want[i : i + 2], 16) for i in (1, 3, 5))
        assert found[stop] == f"{r} {g} {b}", (
            f"{selector} --brand-{stop} is {found[stop]!r}, "
            f"but the shipped colour {want} is {r} {g} {b}"
        )


@pytest.mark.parametrize("selector", [":root", ".dark"])
def test_values_are_channels_not_hexes(css: str, selector: str) -> None:
    """Catches someone 'tidying' a channel triple back into a hex."""
    found = _vars(_block(css, selector))
    assert found
    for stop, value in found.items():
        assert CHANNEL_TRIPLE.match(value), (
            f"{selector} --brand-{stop} is {value!r}; it must be three "
            "space-separated sRGB channels, e.g. '47 90 224'. A hex here "
            "produces rgb(#... / 1), which browsers discard silently."
        )


def test_dark_block_comes_after_root() -> None:
    """Both selectors match <html> at equal specificity, so order decides.

    Put .dark first and a customer's dark ramp is overridden by their light
    one, in dark mode only.
    """
    css = INDEX_CSS.read_text(encoding="utf-8")
    assert css.index(":root") < css.index(".dark")


def test_tailwind_brand_scale_uses_the_rgb_var_form() -> None:
    config = TAILWIND_CONFIG.read_text(encoding="utf-8")
    brand = re.search(r"brand:\s*\{(.*?)\n\s*\},", config, re.S)
    assert brand, "no brand scale found in tailwind.config.js"
    body = brand.group(1)

    entries = dict(re.findall(r"(\d+):\s*\"([^\"]+)\"", body))
    assert set(entries) == {str(s) for s in STOPS}
    for stop, value in entries.items():
        assert value == f"rgb(var(--brand-{stop}) / <alpha-value>)", (
            f"brand.{stop} is {value!r}"
        )


def test_no_hex_remains_in_the_tailwind_brand_scale() -> None:
    config = TAILWIND_CONFIG.read_text(encoding="utf-8")
    brand = re.search(r"brand:\s*\{(.*?)\n\s*\},", config, re.S)
    assert brand
    assert not re.search(r"#[0-9a-fA-F]{6}", brand.group(1))
