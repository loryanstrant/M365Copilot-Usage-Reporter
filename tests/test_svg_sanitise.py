"""The SVG sanitiser: nothing executable survives, every real logo does.

Both halves matter. A sanitiser that strips too little serves an attacker's
file back from our origin; one that strips too much turns every uploaded logo
into a blank box, which nobody notices until a customer complains that their
branding "didn't save".
"""
from __future__ import annotations

import pytest

from shared.svg_safe import UnsafeSvgError, sanitise_svg

PLAIN = b"""<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 72">
  <title>Avanoso</title>
  <defs><linearGradient id="g1"><stop offset="0" stop-color="#ff5800"/></linearGradient></defs>
  <path d="M24 0 L48 48 L0 48 Z" fill="url(#g1)"/>
  <text x="74" y="49" font-size="40" fill="#1f2937">avanoso</text>
</svg>"""


def test_a_plain_exported_svg_survives_with_its_geometry_intact() -> None:
    """The regression guard against an over-eager allow-list.

    Without this, a later tightening quietly empties every uploaded logo and
    the symptom is "branding doesn't work", miles from the cause.
    """
    out = sanitise_svg(PLAIN).decode()
    assert "<path" in out
    assert 'd="M24 0 L48 48 L0 48 Z"' in out
    assert "linearGradient" in out
    assert "avanoso" in out
    assert 'fill="#1f2937"' in out


def test_fragment_href_is_kept_so_gradients_still_work() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<use href="#mark"/></svg>'
    )
    assert b'href="#mark"' in sanitise_svg(svg)


def test_script_element_is_refused() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<script>alert(document.cookie)</script></svg>'
    )
    with pytest.raises(UnsafeSvgError, match="script"):
        sanitise_svg(svg)


def test_foreign_object_is_refused() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject>'
        b'<body xmlns="http://www.w3.org/1999/xhtml">hi</body>'
        b"</foreignObject></svg>"
    )
    with pytest.raises(UnsafeSvgError):
        sanitise_svg(svg)


def test_animation_elements_are_refused() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<set attributeName="onload" to="alert(1)"/></svg>'
    )
    with pytest.raises(UnsafeSvgError):
        sanitise_svg(svg)


def test_onload_attribute_is_stripped_and_the_output_differs() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
        b'<path d="M0 0 L1 1" onclick="alert(2)"/></svg>'
    )
    out = sanitise_svg(svg)
    assert b"onload" not in out
    assert b"onclick" not in out
    assert out != svg, "the stored bytes must be the rewrite, not the original"
    assert b"M0 0 L1 1" in out, "the drawing itself must survive"


def test_external_href_is_stripped() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<use href="https://evil.example/x.svg#a"/></svg>'
    )
    out = sanitise_svg(svg)
    assert b"evil.example" not in out


def test_a_style_element_keeps_its_rules_but_loses_its_fetches() -> None:
    """The element is kept; only what it could fetch is removed.

    It used to be deleted outright, which was worse than the risk — see
    test_an_internal_css_export_keeps_its_colours.
    """
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b"<style>@import url(https://evil.example/x.css);</style>"
        b'<path d="M0 0"/></svg>'
    )
    out = sanitise_svg(svg)
    assert b"@import" not in out
    assert b"evil.example" not in out
    assert b"M0 0" in out


def test_style_attribute_is_dropped_but_presentation_attributes_survive() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<path d="M0 0" style="background:url(https://evil.example/x)" fill="#ff5800"/>'
        b"</svg>"
    )
    out = sanitise_svg(svg)
    assert b"evil.example" not in out
    assert b'fill="#ff5800"' in out


def test_javascript_url_in_an_attribute_is_stripped() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<path d="M0 0" fill="javascript:alert(1)"/></svg>'
    )
    assert b"javascript:" not in sanitise_svg(svg)


def test_entity_declaration_is_refused_without_expanding_it() -> None:
    """A billion-laughs payload is small on disk and vast in memory.

    expat does not fetch external entities but does expand internal ones, so
    the 1 MB upload cap would not save us. Refusing the declaration outright
    is what makes the stdlib parser safe to use here.
    """
    bomb = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE svg [<!ENTITY a "aaaaaaaaaa">'
        b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">'
        b'<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg"><title>&c;</title></svg>'
    )
    with pytest.raises(UnsafeSvgError):
        sanitise_svg(bomb)


def test_a_plain_doctype_is_tolerated() -> None:
    """Old exporters emit one; it carries no entities and no risk."""
    svg = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
        b'"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">'
        b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
    )
    assert b"M0 0" in sanitise_svg(svg)


def test_non_svg_root_is_refused() -> None:
    with pytest.raises(UnsafeSvgError):
        sanitise_svg(b"<html><body>not a logo</body></html>")


def test_unparseable_input_is_refused_with_a_plain_message() -> None:
    with pytest.raises(UnsafeSvgError) as exc:
        sanitise_svg(b"<svg xmlns='http://www.w3.org/2000/svg'><path")
    assert "re-export" in str(exc.value)


def test_messages_never_mention_parser_internals() -> None:
    """Every message is read by an admin, not by the author."""
    bad_inputs = [
        b"<html></html>",
        b"<svg xmlns='http://www.w3.org/2000/svg'><script>x</script></svg>",
        b"\xff\xfe\x00not utf8 at all",
        b"<svg",
    ]
    for raw in bad_inputs:
        with pytest.raises(UnsafeSvgError) as exc:
            sanitise_svg(raw)
        message = str(exc.value).lower()
        for banned in ("traceback", "parseerror", "expat", "mime", "utf-8 codec"):
            assert banned not in message, f"{message!r} leaks {banned}"


def test_the_shipped_sample_logos_survive_sanitising() -> None:
    """The fixtures the feature is demonstrated with must actually pass."""
    from pathlib import Path

    sample_dir = Path(__file__).resolve().parent.parent / "docs" / "branding-sample"
    for name in ("avanoso-light.svg", "avanoso-dark.svg"):
        out = sanitise_svg((sample_dir / name).read_bytes()).decode()
        assert "avanos" in out
        assert "<path" in out


# --- <style> blocks ------------------------------------------------------
# Dropping the element outright used to pass validation and then serve the
# customer a black logo, because the class names on the shapes survived and the
# rules that coloured them did not. Illustrator's "Internal CSS" export and
# several Figma paths produce exactly this shape, so it is the common case, not
# an exotic one.
ILLUSTRATOR_INTERNAL_CSS = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    b"<defs><style>.cls-1{fill:#ff5800}</style></defs>"
    b'<path class="cls-1" d="M0 0 L10 10"/></svg>'
)


def test_an_internal_css_export_keeps_its_colours() -> None:
    out = sanitise_svg(ILLUSTRATOR_INTERNAL_CSS).decode()
    assert "cls-1" in out, "the class on the shape survived"
    assert "#ff5800" in out, "but the rule that colours it did not — logo renders black"


def test_style_block_loses_imports_and_external_urls() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg"><style>'
        b"@import url(https://evil.example/x.css);"
        b".a{fill:#fff;background:url(http://evil.example/y.png)}"
        b".b{fill:url(#grad1)}"
        b'</style><path class="a" d="M0 0"/></svg>'
    )
    out = sanitise_svg(svg).decode()
    assert "evil.example" not in out
    assert "@import" not in out
    assert "url(#grad1)" in out, "a same-document reference must survive"
    assert "#fff" in out, "ordinary declarations must survive"


@pytest.mark.parametrize(
    "css",
    [
        b".a{background:url(javascript:alert(1))}",
        b".a{width:expression(alert(1))}",
        b".a{-moz-binding:url(#x)}",
        b".a{behavior:url(#default#time2)}",
    ],
)
def test_hostile_css_is_refused_not_quietly_rewritten(css: bytes) -> None:
    """Checked against the ORIGINAL text.

    Scrubbing first would turn `url(javascript:...)` into `none` and accept the
    file — safe by accident, but an admin who uploaded a scripted file should be
    told rather than served something subtly different.
    """
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><style>' + css + b"</style></svg>"
    with pytest.raises(UnsafeSvgError):
        sanitise_svg(svg)


# --- namespace -----------------------------------------------------------
def test_a_namespaceless_svg_gets_its_namespace_back() -> None:
    """Valid inline in HTML, which auto-namespaces; broken served standalone."""
    out = sanitise_svg(
        b'<svg viewBox="0 0 10 10"><path d="M0 0" fill="#ff5800"/></svg>'
    ).decode()
    assert "http://www.w3.org/2000/svg" in out
    assert "M0 0" in out


# --- URL schemes ---------------------------------------------------------
@pytest.mark.parametrize(
    "attr",
    [
        b'filter="url(//evil.example/f)"',       # protocol-relative
        b'fill="url(https://evil.example/g)"',
        b'mask="url(http://evil.example/m)"',
    ],
)
def test_external_references_in_any_attribute_are_stripped(attr: bytes) -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0" ' + attr + b"/></svg>"
    )
    assert b"evil.example" not in sanitise_svg(svg)


def test_a_utf8_bom_does_not_break_a_valid_svg() -> None:
    """Windows editors emit one; it must not look like a corrupt file."""
    svg = b"\xef\xbb\xbf" + (
        b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0 L1 1"/></svg>'
    )
    assert b"M0 0 L1 1" in sanitise_svg(svg)
