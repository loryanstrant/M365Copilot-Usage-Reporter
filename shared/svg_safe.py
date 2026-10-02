"""Reduce an uploaded SVG to a presentation-only allow-list.

An admin uploads a logo and the app serves it back. SVG is a scripting format,
so the bytes that arrive are not the bytes we store: this module **rewrites**
the file and the rewrite is what goes in the database. Validate-and-store would
leave anything the checker failed to think of sitting in the payload;
rewrite-and-store means only what the allow-list knows about can survive.

In the app itself a logo is only ever loaded through an ``<img>`` tag, where no
browser executes SVG script. This is the second of three locks — the others
being that ``<img>`` context, and the restrictive Content-Security-Policy the
logo route sets for anyone who opens the URL directly.

Deliberately stdlib-only. ``defusedxml`` would be the right library if one were
warranted, but ``Dockerfile`` hand-duplicates the dependency list with a comment
admitting the drift is not test-covered, so a package for ~70 lines of parsing
is a worse trade than the parsing.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"

# Shapes, grouping and paint. Everything that draws, nothing that acts.
ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        "svg", "g", "defs", "symbol", "use", "title", "desc",
        "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
        "text", "tspan", "textPath",
        "linearGradient", "radialGradient", "stop",
        "clipPath", "mask", "pattern", "metadata",
    }
)

# Present at all => refuse the upload. An admin who exported a scripted SVG
# should be told their file was rejected, not quietly served a different one
# that no longer looks like their logo.
FORBIDDEN_TAGS: frozenset[str] = frozenset(
    {
        "script", "foreignObject", "handler", "iframe", "embed", "object",
        "set", "animate", "animateTransform", "animateMotion", "animateColor",
        "audio", "video", "image",
    }
)

# `style` is excluded from ALLOWED_TAGS on purpose: a <style> child can carry
# @import and url(), which reach the network from inside a "static" image.

_ENTITY_RE = re.compile(r"<!ENTITY", re.I)
_DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>\[]*>", re.I)
_DOCTYPE_SUBSET_RE = re.compile(r"<!DOCTYPE[^>]*\[", re.I)
_URL_SCHEMES_RE = re.compile(r"javascript:|data:text/html|url\(\s*['\"]?https?:", re.I)


class UnsafeSvgError(ValueError):
    """Raised when an SVG carries something we will not serve back."""


def _local(tag: str) -> str:
    """Strip the namespace: ``{http://...}path`` -> ``path``."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _clean_attributes(element: ET.Element) -> None:
    for name in list(element.attrib):
        local = _local(name).lower()
        value = element.attrib[name]

        # Event handlers: onload, onclick, onmouseover, ...
        if local.startswith("on"):
            del element.attrib[name]
            continue

        # Links may only point inside this document (href="#gradient-1"), which
        # is what gradients, clip paths and <use> actually need. Anything else
        # is a fetch from a file we do not control.
        if local in {"href", "xlink:href"} or local == "href":
            if not value.strip().startswith("#"):
                del element.attrib[name]
            continue

        # Inline CSS can carry url() and behaviour; presentation attributes
        # (fill, stroke, opacity) survive and cover every real logo.
        if local == "style":
            del element.attrib[name]
            continue

        if _URL_SCHEMES_RE.search(value):
            del element.attrib[name]


def _walk(parent: ET.Element) -> None:
    for child in list(parent):
        local = _local(child.tag)
        if local in FORBIDDEN_TAGS:
            raise UnsafeSvgError(local)
        if local not in ALLOWED_TAGS:
            parent.remove(child)
            continue
        _clean_attributes(child)
        _walk(child)


def sanitise_svg(raw: bytes) -> bytes:
    """Return a rewritten, presentation-only SVG.

    Raises ``UnsafeSvgError`` with a message written for the admin who uploaded
    it — no tag names they did not type, no parser internals.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsafeSvgError(
            "We couldn't read that SVG. Please re-export it and try again."
        ) from exc

    # Entity declarations go before the parser sees them. expat does not fetch
    # *external* entities, but it does expand internal ones, so a 1 MB file can
    # still be a billion-laughs bomb that never reaches the size check. No real
    # exporter (Illustrator, Figma, Inkscape) emits an internal subset.
    if _ENTITY_RE.search(text) or _DOCTYPE_SUBSET_RE.search(text):
        raise UnsafeSvgError(
            "That SVG uses a feature we can't accept safely. "
            "Please re-export it from your design tool."
        )
    text = _DOCTYPE_RE.sub("", text)

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise UnsafeSvgError(
            "We couldn't read that SVG. Please re-export it and try again."
        ) from exc

    if _local(root.tag) != "svg":
        raise UnsafeSvgError(
            "That file isn't an SVG image. Please choose a PNG, JPEG or SVG."
        )

    try:
        _clean_attributes(root)
        _walk(root)
    except UnsafeSvgError as exc:
        offender = str(exc)
        if offender in {"script", "handler"}:
            raise UnsafeSvgError(
                "That SVG contains a script, which we can't accept. "
                "Please export a plain SVG."
            ) from exc
        raise UnsafeSvgError(
            "That SVG contains something we can't display safely "
            f"(a <{offender}> element). Please export a plain SVG."
        ) from exc

    ET.register_namespace("", SVG_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=False)
