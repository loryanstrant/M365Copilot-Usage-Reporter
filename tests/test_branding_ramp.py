"""The brand ramp derivation: readable for any seed, in both modes.

The tests that matter here are the ones over the whole hue circle. A single
check against the default blue would pass for an implementation that is
unreadable for yellow, and "somebody picks yellow" is the scenario this feature
exists to survive.
"""
from __future__ import annotations

import pytest

from shared.branding import (
    DARK_ACCENT_STOP,
    DARK_SURFACE,
    DEFAULT_RAMP_HEX,
    LIGHT_ACCENT_STOP,
    LIGHT_SURFACE,
    MIN_CONTRAST,
    STOPS,
    BrandingError,
    contrast_ratio,
    derive_ramps,
    hex_to_oklch,
    normalise_hex,
    oklch_to_hex,
    ramp_to_channels,
    relative_luminance,
)

# 24 hues around the circle, plus the achromatic extremes and the two colours
# that carry real meaning for this project (the product's own blue, and the
# Avanade orange used by the Avanoso sample brand).
SEEDS: list[str] = [
    "#ff0000", "#ff4000", "#ff8000", "#ffbf00", "#ffff00", "#bfff00",
    "#80ff00", "#40ff00", "#00ff00", "#00ff40", "#00ff80", "#00ffbf",
    "#00ffff", "#00bfff", "#0080ff", "#0040ff", "#0000ff", "#4000ff",
    "#8000ff", "#bf00ff", "#ff00ff", "#ff00bf", "#ff0080", "#ff0040",
    "#000000", "#ffffff", "#7f7f7f",
    "#2f5ae0",  # the product default
    "#ff5800",  # Avanade orange, the Avanoso sample brand
]


@pytest.mark.parametrize("seed", SEEDS)
def test_light_accent_meets_wcag_aa_on_white(seed: str) -> None:
    """Primary buttons and links must be readable on a white card."""
    brand = derive_ramps(seed)
    ratio = contrast_ratio(brand.light[LIGHT_ACCENT_STOP], LIGHT_SURFACE)
    assert ratio >= MIN_CONTRAST, f"{seed}: light accent only {ratio:.2f}:1"


@pytest.mark.parametrize("seed", SEEDS)
def test_dark_accent_meets_wcag_aa_on_slate_900(seed: str) -> None:
    """After any lift, the dark accent must be readable on the dark page."""
    brand = derive_ramps(seed)
    ratio = contrast_ratio(brand.dark[DARK_ACCENT_STOP], DARK_SURFACE)
    assert ratio >= MIN_CONTRAST, f"{seed}: dark accent only {ratio:.2f}:1"
    assert brand.dark_accent_contrast == pytest.approx(ratio, abs=1e-6)


@pytest.mark.parametrize("seed", SEEDS)
def test_light_side_never_needs_a_lift(seed: str) -> None:
    """Pinning lightness at the accent stop is what makes the light side safe.

    If this ever fails, the lightness curve has been retuned and the light side
    now needs its own lift mechanism — which does not exist. Better to find out
    here than from a customer with an unreadable button.
    """
    brand = derive_ramps(seed)
    assert brand.light_accent_contrast >= MIN_CONTRAST


@pytest.mark.parametrize("seed", SEEDS)
def test_both_ramps_are_monotonic(seed: str) -> None:
    """Luminance must fall from 50 to 950 — a lift must never invert the ramp.

    An inverted ramp is subtle and nasty: hover states go lighter instead of
    darker and borders stop reading as borders, with no error anywhere.
    """
    brand = derive_ramps(seed)
    for name, ramp in (("light", brand.light), ("dark", brand.dark)):
        lums = [relative_luminance(ramp[s]) for s in STOPS]
        for i in range(len(lums) - 1):
            assert lums[i] > lums[i + 1], (
                f"{seed} {name}: stop {STOPS[i]} is not lighter than {STOPS[i + 1]}"
            )


@pytest.mark.parametrize("seed", SEEDS)
def test_every_stop_is_a_valid_srgb_hex(seed: str) -> None:
    brand = derive_ramps(seed)
    for ramp in (brand.light, brand.dark):
        assert set(ramp) == set(STOPS)
        for value in ramp.values():
            assert normalise_hex(value) == value


@pytest.mark.parametrize("seed", SEEDS)
def test_derivation_is_deterministic(seed: str) -> None:
    assert derive_ramps(seed) == derive_ramps(seed)


def test_default_seed_reproduces_the_shipped_ramp_within_tolerance() -> None:
    """Faithful to the product's palette, but NOT byte-identical to it.

    This is exactly why frontend/src/index.css keeps literal default values
    instead of calling this function: a derived default would shift the
    unbranded product's colours by a channel or two for no reason.
    """
    brand = derive_ramps("#2f5ae0")
    assert brand.light[600] == DEFAULT_RAMP_HEX[600], "the anchor stop must be exact"
    for stop in STOPS:
        got = tuple(int(brand.light[stop][i : i + 2], 16) for i in (1, 3, 5))
        want = tuple(int(DEFAULT_RAMP_HEX[stop][i : i + 2], 16) for i in (1, 3, 5))
        for a, b in zip(got, want):
            assert abs(a - b) <= 5, f"stop {stop}: {brand.light[stop]} vs {DEFAULT_RAMP_HEX[stop]}"


def test_dark_lift_is_reported_honestly() -> None:
    """The UI tells the admin when we changed their colour, so it must know."""
    lifted = derive_ramps("#8b00ff")  # violet: measured to need a lift
    assert lifted.dark_accent_lifted is True
    assert lifted.dark_accent_lift > 0.0
    assert lifted.dark[DARK_ACCENT_STOP] != lifted.light[DARK_ACCENT_STOP]

    unlifted = derive_ramps("#00a300")  # green: measured to need none
    assert unlifted.dark_accent_lifted is False
    assert unlifted.dark_accent_lift == 0.0
    assert unlifted.dark == unlifted.light


def test_gradient_gate_flags_the_product_default() -> None:
    """White on the sign-in gradient's lightest point is a real failure case.

    The product's own blue measures 4.46:1 there — under AA. A branded install
    therefore deepens the gradient, and Avanade orange (4.61:1) does not need
    to. If this test goes green for both, the gate has stopped doing anything.
    """
    blue = derive_ramps("#2f5ae0")
    assert blue.gradient_needs_deepening is True
    assert blue.gradient_contrast < MIN_CONTRAST

    orange = derive_ramps("#ff5800")
    assert orange.gradient_needs_deepening is False
    assert orange.gradient_contrast >= MIN_CONTRAST


@pytest.mark.parametrize("seed", ["#000000", "#ffffff", "#7f7f7f"])
def test_achromatic_seeds_produce_a_usable_grey_ramp(seed: str) -> None:
    """No division by zero when chroma is zero, and still readable."""
    brand = derive_ramps(seed)
    assert brand.light_accent_contrast >= MIN_CONTRAST
    assert brand.dark_accent_contrast >= MIN_CONTRAST


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2f5ae0", "#2f5ae0"),
        ("#2F5AE0", "#2f5ae0"),
        ("  #2f5ae0 ", "#2f5ae0"),
        ("FF5800", "#ff5800"),
    ],
)
def test_normalise_hex_accepts_the_forms_people_type(raw: str, expected: str) -> None:
    assert normalise_hex(raw) == expected


@pytest.mark.parametrize("raw", ["blue", "#fff", "", "#2f5ae", "#2f5ae0z", None])
def test_normalise_hex_rejects_everything_else(raw: str | None) -> None:
    with pytest.raises(BrandingError):
        normalise_hex(raw)


def test_oklch_round_trip_is_stable() -> None:
    for seed in SEEDS:
        light, chroma, hue = hex_to_oklch(seed)
        assert oklch_to_hex(light, chroma, hue) == normalise_hex(seed)


def test_ramp_to_channels_emits_triples_not_hexes() -> None:
    """The CSS variables must hold channels; a hex there is invalid CSS."""
    channels = ramp_to_channels({"600": "#2f5ae0", "50": "#eef4ff"})
    assert channels == {"600": "47 90 224", "50": "238 244 255"}


def test_as_json_ramps_uses_string_keys() -> None:
    """JSON keys are strings, and the TypeScript side indexes them as strings."""
    light, dark = derive_ramps("#ff5800").as_json_ramps()
    assert set(light) == {str(s) for s in STOPS}
    assert set(dark) == {str(s) for s in STOPS}
    assert all(isinstance(k, str) for k in light)
