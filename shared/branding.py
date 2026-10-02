"""Derive a full brand ramp from the single colour an admin picks.

An admin supplies one hex colour. Tailwind needs eleven stops (50..950), and
dark mode needs its own eleven, because the UI already reaches for *different*
stops per mode (``text-brand-600 dark:text-brand-500``). This module turns one
seed into both, with each accent contrast-checked.

**Why the lightness is not taken from the seed.** The shipped palette is, to
three decimals, already an OKLCH ramp at near-constant hue with a clean
lightness curve. So the recipe is: take *hue and chroma* from the seed and
force *lightness* onto that curve. The admin's colour decides which colour the
app is, not how bright it gets — which is the only reason white text on a
primary button stays readable for a seed of any hue. A naive "scale the seed's
own lightness" approach produces an unreadable button the moment somebody picks
a bright yellow, and that is exactly the kind of thing nobody tests with.

OKLCH rather than HSL for the same reason: equal HSL lightness steps read
wildly differently across hues, so an HSL ramp is readable for blue and
illegible for yellow.

**Why this is Python and not TypeScript.** The public branding payload is
fetched once at app start anyway, so shipping twenty-two finished hexes costs
nothing, and a single implementation cannot drift from a second one. The live
Settings preview calls ``POST /admin/branding/preview`` rather than
reimplementing any of this in the browser.

Deliberately dependency-free: this is arithmetic, and ``Dockerfile``
hand-duplicates the dependency list with a comment admitting the drift is not
test-covered, so a new package here would be a maintenance hazard.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# --- the product's own ramp ----------------------------------------------
# Reference only. It is NEVER served: derive_ramps() reproduces it to within
# 1-4 of 255 per channel but not byte-exactly, so the defaults live as literal
# channel values in frontend/src/index.css and this copy exists so a test can
# assert the two agree. See tests/test_branding_defaults_unchanged.py.
STOPS: tuple[int, ...] = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)

DEFAULT_RAMP_HEX: dict[int, str] = {
    50: "#eef4ff",
    100: "#d9e6ff",
    200: "#bcd3ff",
    300: "#8eb4fc",
    400: "#5c8bf8",
    500: "#3b6ef5",
    600: "#2f5ae0",
    700: "#2647b4",
    800: "#233f8f",
    900: "#1e3670",
    950: "#152245",
}

# --- the curve the shipped ramp traces -----------------------------------
# OKLab lightness per stop, measured off DEFAULT_RAMP_HEX.
RAMP_LIGHTNESS: dict[int, float] = {
    50: 0.9658,
    100: 0.9229,
    200: 0.8645,
    300: 0.7703,
    400: 0.6564,
    500: 0.5823,
    600: 0.5229,
    700: 0.4454,
    800: 0.3962,
    900: 0.3487,
    950: 0.2615,
}

# Chroma as a multiple of the seed's own chroma, taken from the shipped ramp's
# curve relative to its 600 stop (the anchor, where a seed reproduces exactly).
RAMP_CHROMA: dict[int, float] = {
    50: 0.077,
    100: 0.176,
    200: 0.316,
    300: 0.534,
    400: 0.812,
    500: 1.002,
    600: 1.000,
    700: 0.845,
    800: 0.653,
    900: 0.500,
    950: 0.324,
}

LIGHT_SURFACE = "#ffffff"
DARK_SURFACE = "#0f172a"  # slate-900, the app's dark page background
LIGHT_ACCENT_STOP = 600  # what `text-brand-600` / `bg-brand-600` use
DARK_ACCENT_STOP = 500  # what `dark:text-brand-500` uses
GRADIENT_LIGHTEST_STOP = 500  # the sign-in panel's `to-brand-500` end

MIN_CONTRAST = 4.5  # WCAG 2.1 AA, normal text
LIFT_STEP = 0.01  # OKLab L added per iteration
LIFT_MAX = 0.20  # a guard, not a working range: observed lifts are <= 0.06

# Spreading the lift across the accent region keeps the ramp monotonic. Stops
# 50-200 and 800-950 are untouched on purpose: dark mode uses the high stops as
# *surfaces* (bg-brand-900/20, border-brand-700), not as text, so brightening
# them would wash out panels to fix a text problem they do not have.
LIFT_TAPER: dict[int, float] = {300: 0.40, 400: 0.75, 500: 1.00, 600: 0.75, 700: 0.40}


class BrandingError(ValueError):
    """Raised when a supplied colour is not a usable hex value."""


@dataclass(frozen=True)
class DerivedBrand:
    """Both ramps for one seed colour, with the contrast facts behind them."""

    seed_hex: str
    light: dict[int, str] = field(default_factory=dict)
    dark: dict[int, str] = field(default_factory=dict)
    light_accent_contrast: float = 0.0
    dark_accent_contrast: float = 0.0
    dark_accent_lifted: bool = False
    dark_accent_lift: float = 0.0
    # White heading text sits on the sign-in panel's gradient, whose lightest
    # point is stop 500. When that falls below AA the panel renders one stop
    # deeper (from-brand-800 via-brand-700 to-brand-600). This is not
    # hypothetical: the product's own blue measures 4.46:1 there.
    gradient_needs_deepening: bool = False
    gradient_contrast: float = 0.0

    def as_json_ramps(self) -> tuple[dict[str, str], dict[str, str]]:
        """Both ramps keyed by stop-as-string, ready for JSON.

        JSON object keys are strings, so the API and the client agree on a
        string key end to end — a ``Record<number, string>`` on the TypeScript
        side type-checks and then indexes wrong at runtime.
        """
        return (
            {str(s): self.light[s] for s in STOPS},
            {str(s): self.dark[s] for s in STOPS},
        )


# --- hex helpers ----------------------------------------------------------
def normalise_hex(value: str | None) -> str:
    """Accept the forms people actually type; return a lowercase ``#rrggbb``.

    Three-digit shorthand is rejected rather than expanded: an admin typing
    ``#fff`` far more likely mistyped something than wanted pure white, and a
    wrong brand colour is more annoying to discover than an error message.
    """
    if value is None:
        raise BrandingError("No colour was supplied.")
    text = value.strip().lstrip("#").lower()
    if len(text) != 6 or any(c not in "0123456789abcdef" for c in text):
        raise BrandingError(
            f'"{value.strip()}" isn\'t a colour code. '
            "Use a six-digit hex value like #2f5ae0."
        )
    return f"#{text}"


def _channels(value: str) -> tuple[int, int, int]:
    h = value.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _srgb_to_linear(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> int:
    c = max(0.0, min(1.0, c))
    v = c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
    return round(max(0.0, min(1.0, v)) * 255)


# OKLab matrices (Björn Ottosson). _M1/_M2 forward, _M1_INV/_M2_INV back.
_M1 = (
    (0.4122214708, 0.5363325363, 0.0514459929),
    (0.2119034982, 0.6806995451, 0.1073969566),
    (0.0883024619, 0.2817188376, 0.6299787005),
)
_M2 = (
    (0.2104542553, 0.7936177850, -0.0040720468),
    (1.9779984951, -2.4285922050, 0.4505937099),
    (0.0259040371, 0.7827717662, -0.8086757660),
)
_M1_INV = (
    (4.0767416621, -3.3077115913, 0.2309699292),
    (-1.2684380046, 2.6097574011, -0.3413193965),
    (-0.0041960863, -0.7034186147, 1.7076147010),
)
_M2_INV = (
    (1.0, 0.3963377774, 0.2158037573),
    (1.0, -0.1055613458, -0.0638541728),
    (1.0, -0.0894841775, -1.2914855480),
)


def _apply(matrix: tuple[tuple[float, ...], ...], v: tuple[float, float, float]):
    return tuple(sum(matrix[i][j] * v[j] for j in range(3)) for i in range(3))


def hex_to_oklch(value: str) -> tuple[float, float, float]:
    """``#rrggbb`` -> (lightness 0..1, chroma, hue degrees)."""
    lin = tuple(_srgb_to_linear(c) for c in _channels(normalise_hex(value)))
    lms = _apply(_M1, lin)  # type: ignore[arg-type]
    lms = tuple(math.copysign(abs(x) ** (1 / 3), x) for x in lms)
    light, a, b = _apply(_M2, lms)  # type: ignore[arg-type]
    return light, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def _oklch_to_linear(light: float, chroma: float, hue: float):
    rad = math.radians(hue)
    lab = (light, chroma * math.cos(rad), chroma * math.sin(rad))
    lms = _apply(_M2_INV, lab)
    lms = tuple(x**3 for x in lms)
    return _apply(_M1_INV, lms)  # type: ignore[arg-type]


def oklch_to_hex(light: float, chroma: float, hue: float) -> str:
    """Convert to sRGB, reducing chroma until the colour is in gamut.

    Clipping each channel independently would shift the hue, so chroma is
    binary-searched down instead — the colour stays the colour, it just gets
    less saturated until the monitor can show it.
    """
    lin = _oklch_to_linear(light, chroma, hue)
    if not all(-1e-4 <= x <= 1 + 1e-4 for x in lin):
        low, high = 0.0, chroma
        lin = _oklch_to_linear(light, 0.0, hue)
        for _ in range(40):
            mid = (low + high) / 2
            candidate = _oklch_to_linear(light, mid, hue)
            if all(-1e-4 <= x <= 1 + 1e-4 for x in candidate):
                low, lin = mid, candidate
            else:
                high = mid
    r, g, b = (_linear_to_srgb(x) for x in lin)
    return f"#{r:02x}{g:02x}{b:02x}"


def relative_luminance(value: str) -> float:
    """WCAG 2.1 relative luminance."""
    r, g, b = (_srgb_to_linear(c) for c in _channels(normalise_hex(value)))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    """WCAG 2.1 contrast ratio between two colours; 1.0 .. 21.0."""
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# --- the derivation -------------------------------------------------------
def _ramp(chroma: float, hue: float, lift: float = 0.0) -> dict[int, str]:
    return {
        stop: oklch_to_hex(
            RAMP_LIGHTNESS[stop] + LIFT_TAPER.get(stop, 0.0) * lift,
            chroma * RAMP_CHROMA[stop],
            hue,
        )
        for stop in STOPS
    }


def derive_ramps(seed_hex: str) -> DerivedBrand:
    """Turn one colour into a light ramp, a dark ramp and the contrast facts.

    Deterministic: the same seed always gives the same result.
    """
    seed = normalise_hex(seed_hex)
    _, chroma, hue = hex_to_oklch(seed)

    light = _ramp(chroma, hue)

    # The light side has never needed a lift in testing (measured 5.07-6.41:1
    # across the hue circle) because lightness is pinned at the accent stop.
    # tests/test_branding_ramp.py asserts that stays true rather than assuming
    # it, so if the curve is ever retuned the failure is explicit.
    dark = dict(light)
    lift = 0.0
    while (
        contrast_ratio(dark[DARK_ACCENT_STOP], DARK_SURFACE) < MIN_CONTRAST
        and lift < LIFT_MAX
    ):
        lift = round(lift + LIFT_STEP, 4)
        dark = _ramp(chroma, hue, lift)

    gradient_contrast = contrast_ratio(LIGHT_SURFACE, light[GRADIENT_LIGHTEST_STOP])

    return DerivedBrand(
        seed_hex=seed,
        light=light,
        dark=dark,
        light_accent_contrast=contrast_ratio(light[LIGHT_ACCENT_STOP], LIGHT_SURFACE),
        dark_accent_contrast=contrast_ratio(dark[DARK_ACCENT_STOP], DARK_SURFACE),
        dark_accent_lifted=lift > 0.0,
        dark_accent_lift=lift,
        gradient_needs_deepening=gradient_contrast < MIN_CONTRAST,
        gradient_contrast=gradient_contrast,
    )


def ramp_to_channels(ramp: dict[str, str]) -> dict[str, str]:
    """``{"600": "#2f5ae0"}`` -> ``{"600": "47 90 224"}``.

    The CSS custom properties hold space-separated channels so Tailwind's
    ``<alpha-value>`` slot can emit ``rgb(... / 0.2)``. A hex in the variable
    produces invalid CSS that browsers drop silently.
    """
    out: dict[str, str] = {}
    for stop, value in ramp.items():
        r, g, b = _channels(normalise_hex(value))
        out[stop] = f"{r} {g} {b}"
    return out
