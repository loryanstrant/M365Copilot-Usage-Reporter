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


def test_style_element_is_dropped() -> None:
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
