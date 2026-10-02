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
        # <style> is allowed but its CONTENTS are rewritten — see
        # _clean_style_text. Dropping the element outright (the previous
        # behaviour) was worse than the risk it avoided: Illustrator's
        # "Internal CSS" export and several Figma paths emit
        # <style>.cls-1{fill:#2f5ae0}</style> plus <path class="cls-1">, so
        # removing the rule while keeping the class silently repainted the
        # customer's logo black with no error anywhere.
        "style",
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


_ENTITY_RE = re.compile(r"<!ENTITY", re.I)
_DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>\[]*>", re.I)
_DOCTYPE_SUBSET_RE = re.compile(r"<!DOCTYPE[^>]*\[", re.I)
# Anything that could reach the network or carry markup. Protocol-relative
# `url(//host/x)` is included: it is a real external fetch that an earlier
# version of this pattern missed.
_URL_SCHEMES_RE = re.compile(
    r"javascript:|vbscript:|data:(?!image/(png|jpeg|gif|webp);base64,)"
    r"|url\(\s*['\"]?(?:https?:|//)",
    re.I,
)
# CSS inside a <style> block. Fetches and the ancient IE/Gecko script hooks.
_CSS_IMPORT_RE = re.compile(r"@import[^;}]*;?", re.I)
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(?!#)[^)]*\1\s*\)", re.I)
_CSS_HOSTILE_RE = re.compile(r"javascript:|expression\(|behaviou?r\s*:|-moz-binding", re.I)


class UnsafeSvgError(ValueError):
    """Raised when an SVG carries something we will not serve back."""


def _local(tag: str) -> str:
    """Strip the namespace: ``{http://...}path`` -> ``path``."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _clean_style_text(css: str) -> str:
    """Strip everything from a <style> block that could reach the network.

    What survives is declarations — ``.cls-1{fill:#ff5800}`` — which is the only
    reason the element is allowed at all. What goes: ``@import`` at-rules, every
    ``url(...)`` that is not a same-document ``#fragment``, and the ancient
    IE/Gecko script hooks. A block still carrying something hostile after that
    is refused rather than served half-scrubbed.
    """
    # Check the ORIGINAL text first. Scrubbing before checking would let
    # `url(javascript:...)` be quietly rewritten to `none` and accepted — safe
    # by accident, but an admin who uploaded a scripted file should be told.
    if _CSS_HOSTILE_RE.search(css):
        raise UnsafeSvgError("style")
    cleaned = _CSS_IMPORT_RE.sub("", css)
    cleaned = _CSS_URL_RE.sub("none", cleaned)
    if _CSS_HOSTILE_RE.search(cleaned):
        raise UnsafeSvgError("style")
    return cleaned


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
        if local == "style":
            # Rewrite the CSS rather than drop the element: the class names on
            # the shapes refer to it, so removing it repaints the logo.
            child.text = _clean_style_text(child.text or "")
            child.tail = child.tail
            continue
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
        if offender in {"script", "handler", "style"}:
            raise UnsafeSvgError(
                "That SVG contains a script, which we can't accept. "
                "Please export a plain SVG."
            ) from exc
        raise UnsafeSvgError(
            "That SVG contains something we can't display safely "
            f"(a <{offender}> element). Please export a plain SVG."
        ) from exc

    # An SVG pasted inline into HTML is often written with no xmlns at all —
    # valid there, because HTML auto-namespaces foreign content. Served
    # standalone as image/svg+xml it would not render, so put the namespace
    # back rather than handing the admin a silently broken image.
    if "}" not in root.tag:
        root.set("xmlns", SVG_NS)

    ET.register_namespace("", SVG_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=False)
