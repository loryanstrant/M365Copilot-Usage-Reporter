"""The branding API: public to read, admin to change, bytes that stay bytes.

Three failure modes shape most of what is asserted here:

* the logo bytes leaking into a JSON payload, which would bloat the
  pre-sign-in read every page load makes;
* a replaced logo that browsers never fetch, because its URL did not change;
* an uploaded file being served back as whatever the uploader claimed it was.
"""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from shared.db import SessionLocal
from shared.models import AppConfig, AppUser
from shared.security import hash_password

# A 1x1 PNG and a 1x1 JPEG — real headers, so the magic-byte check is exercised.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000050001" "0d0a2db4" "0000000049454e44ae426082"
)
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
SVG_PLAIN = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    b'<path d="M0 0 L10 10" fill="#ff5800"/></svg>'
)
SVG_WITH_ONLOAD = (
    b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
    b'<path d="M0 0 L10 10"/></svg>'
)
GIF = b"GIF89a" + b"\x00" * 20
HTML_AS_PNG = b"<html><script>alert(1)</script></html>"


@pytest_asyncio.fixture
async def client():
    from api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    async with SessionLocal() as s:
        s.add(AppUser(username="admin", password_hash=hash_password("pw"), role="admin"))
        s.add(AppConfig(id=1))
        await s.commit()
    r = await client.post("/auth/login", json={"username": "admin", "password": "pw"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _upload(content: bytes, name: str, variant: str = "light", plate: bool = False):
    return {
        "files": {"file": (name, content, "application/octet-stream")},
        "data": {"variant": variant, "needs_light_plate": str(plate).lower()},
    }


# --- access ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_branding_is_readable_without_signing_in(client):
    """The sign-in screen itself needs this, so it cannot require a token."""
    r = await client.get("/auth/branding")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/admin/branding"),
        ("PUT", "/admin/branding"),
        ("POST", "/admin/branding/logo"),
        ("POST", "/admin/branding/preview"),
        ("DELETE", "/admin/branding"),
        ("DELETE", "/admin/branding/logo/light"),
    ],
)
async def test_admin_routes_reject_anonymous_callers(client, method, path):
    r = await client.request(method, path, json={})
    assert r.status_code in (401, 403)


# --- the unbranded default ------------------------------------------------
@pytest.mark.asyncio
async def test_unbranded_payload_carries_no_ramp(client):
    """Empty ramps are the signal to leave the CSS defaults completely alone."""
    body = (await client.get("/auth/branding")).json()
    assert body["brand_primary_hex"] is None
    assert body["ramp_light"] == {}
    assert body["ramp_dark"] == {}
    assert body["has_logo_light"] is False
    assert body["logo_light_url"] is None


# --- colour ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_put_colour_normalises_and_persists(client):
    headers = await _admin_headers(client)
    r = await client.put(
        "/admin/branding", json={"brand_primary_hex": "  #FF5800 "}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["brand_primary_hex"] == "#ff5800"

    public = (await client.get("/auth/branding")).json()
    assert public["brand_primary_hex"] == "#ff5800"
    assert public["ramp_light"]["600"].startswith("#")
    assert set(public["ramp_light"]) == set(public["ramp_dark"])
    assert len(public["ramp_light"]) == 11


@pytest.mark.asyncio
async def test_a_colour_that_is_not_a_colour_is_refused_plainly(client):
    headers = await _admin_headers(client)
    r = await client.put(
        "/admin/branding", json={"brand_primary_hex": "blue"}, headers=headers
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "#2f5ae0" in detail  # it shows them the shape of a right answer
    assert "Traceback" not in detail


@pytest.mark.asyncio
async def test_org_name_reaches_the_public_payload(client):
    headers = await _admin_headers(client)
    await client.put(
        "/admin/branding", json={"org_display_name": "Avanoso"}, headers=headers
    )
    assert (await client.get("/auth/branding")).json()["org_display_name"] == "Avanoso"


@pytest.mark.asyncio
async def test_preview_derives_without_persisting(client):
    headers = await _admin_headers(client)
    r = await client.post(
        "/admin/branding/preview", json={"brand_primary_hex": "#ff5800"}, headers=headers
    )
    assert r.status_code == 200
    assert len(r.json()["ramp_dark"]) == 11
    assert r.json()["dark_accent_contrast"] >= 4.5
    # Nothing was saved.
    assert (await client.get("/auth/branding")).json()["brand_primary_hex"] is None


# --- logo upload and serving ----------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content,name,mime",
    [(PNG, "logo.png", "image/png"), (JPEG, "logo.jpg", "image/jpeg")],
)
async def test_raster_logo_round_trips(client, content, name, mime):
    headers = await _admin_headers(client)
    r = await client.post(
        "/admin/branding/logo", **_upload(content, name), headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["has_logo_light"] is True

    got = await client.get("/auth/branding/logo/light")
    assert got.status_code == 200
    assert got.headers["content-type"].startswith(mime)
    assert got.content == content
    assert got.headers["etag"]
    assert "default-src 'none'" in got.headers["content-security-policy"]
    assert got.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_logo_is_not_served_from_the_immutable_cache(client):
    """A logo cached forever would make a replacement invisible to the browser."""
    headers = await _admin_headers(client)
    await client.post("/admin/branding/logo", **_upload(PNG, "logo.png"), headers=headers)
    cache = (await client.get("/auth/branding/logo/light")).headers["cache-control"]
    assert "must-revalidate" in cache
    assert "immutable" not in cache


@pytest.mark.asyncio
async def test_etag_returns_304(client):
    headers = await _admin_headers(client)
    await client.post("/admin/branding/logo", **_upload(PNG, "logo.png"), headers=headers)
    first = await client.get("/auth/branding/logo/light")
    again = await client.get(
        "/auth/branding/logo/light", headers={"If-None-Match": first.headers["etag"]}
    )
    assert again.status_code == 304
    assert not again.content


@pytest.mark.asyncio
async def test_logo_url_changes_when_the_logo_changes(client):
    """Without this, a replaced logo sits in browser caches indefinitely."""
    headers = await _admin_headers(client)
    first = await client.post(
        "/admin/branding/logo", **_upload(PNG, "logo.png"), headers=headers
    )
    second = await client.post(
        "/admin/branding/logo", **_upload(JPEG, "logo.jpg"), headers=headers
    )
    assert first.json()["logo_light_url"] != second.json()["logo_light_url"]


@pytest.mark.asyncio
async def test_missing_logo_is_a_json_404_not_index_html(client):
    r = await client.get("/auth/branding/logo/dark")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert "<html" not in r.text.lower()


@pytest.mark.asyncio
async def test_unknown_variant_is_refused(client):
    assert (await client.get("/auth/branding/logo/sideways")).status_code == 400


# --- what must not be stored ---------------------------------------------
@pytest.mark.asyncio
async def test_oversized_upload_is_refused_with_413(client):
    headers = await _admin_headers(client)
    too_big = PNG + b"\x00" * (1024 * 1024 + 10)
    r = await client.post(
        "/admin/branding/logo", **_upload(too_big, "big.png"), headers=headers
    )
    assert r.status_code == 413
    assert "1 MB" in r.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content,name", [(GIF, "logo.gif"), (HTML_AS_PNG, "logo.png")]
)
async def test_a_file_that_is_not_an_image_is_refused(client, content, name):
    """Including HTML renamed .png — the extension is a claim, not a fact."""
    headers = await _admin_headers(client)
    r = await client.post(
        "/admin/branding/logo", **_upload(content, name), headers=headers
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "Traceback" not in detail
    assert "mime" not in detail.lower()


@pytest.mark.asyncio
async def test_svg_is_stored_sanitised(client):
    headers = await _admin_headers(client)
    r = await client.post(
        "/admin/branding/logo", **_upload(SVG_WITH_ONLOAD, "logo.svg"), headers=headers
    )
    assert r.status_code == 200
    served = await client.get("/auth/branding/logo/light")
    assert b"onload" not in served.content
    assert b"M0 0 L10 10" in served.content, "the drawing must survive"
    assert served.headers["content-type"].startswith("image/svg+xml")


@pytest.mark.asyncio
async def test_a_scripted_svg_is_refused_outright(client):
    headers = await _admin_headers(client)
    scripted = (
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    )
    r = await client.post(
        "/admin/branding/logo", **_upload(scripted, "logo.svg"), headers=headers
    )
    assert r.status_code == 400
    assert "script" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_logo_bytes_never_appear_in_json(client):
    """The pre-sign-in payload is fetched on every page load; keep it small."""
    headers = await _admin_headers(client)
    await client.post("/admin/branding/logo", **_upload(PNG, "logo.png"), headers=headers)

    for response in (
        await client.get("/auth/branding"),
        await client.get("/admin/branding", headers=headers),
    ):
        assert b"\x89PNG" not in response.content
        assert "iVBORw0" not in response.text  # not base64 either
        assert response.json()["has_logo_light"] is True


# --- removal --------------------------------------------------------------
@pytest.mark.asyncio
async def test_deleting_one_logo_leaves_the_other(client):
    headers = await _admin_headers(client)
    await client.post("/admin/branding/logo", **_upload(PNG, "l.png"), headers=headers)
    await client.post(
        "/admin/branding/logo", **_upload(SVG_PLAIN, "d.svg", variant="dark"), headers=headers
    )
    r = await client.delete("/admin/branding/logo/dark", headers=headers)
    assert r.json()["has_logo_dark"] is False
    assert r.json()["has_logo_light"] is True


@pytest.mark.asyncio
async def test_reset_clears_colour_name_and_both_logos(client):
    headers = await _admin_headers(client)
    await client.put(
        "/admin/branding",
        json={"brand_primary_hex": "#ff5800", "org_display_name": "Avanoso"},
        headers=headers,
    )
    await client.post("/admin/branding/logo", **_upload(PNG, "l.png"), headers=headers)
    await client.post(
        "/admin/branding/logo", **_upload(SVG_PLAIN, "d.svg", variant="dark"), headers=headers
    )

    r = await client.delete("/admin/branding", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["brand_primary_hex"] is None
    assert body["org_display_name"] is None
    assert body["has_logo_light"] is False
    assert body["has_logo_dark"] is False
    assert (await client.get("/auth/branding")).json()["ramp_light"] == {}


@pytest.mark.asyncio
async def test_the_light_plate_preference_round_trips(client):
    headers = await _admin_headers(client)
    r = await client.post(
        "/admin/branding/logo", **_upload(PNG, "l.png", plate=True), headers=headers
    )
    assert r.json()["logo_light_needs_plate"] is True
    assert (await client.get("/auth/branding")).json()["logo_light_needs_plate"] is True


# --- the design decision this pins ---------------------------------------
def test_app_config_carries_no_image_bytes():
    """Logos live in their own table, on purpose.

    ``session.get(AppConfig, 1)`` runs on nearly every request including the
    public pre-sign-in config read, and loads every column. Moving the images
    onto this row would widen the hottest read in the app to 2 MB. If someone
    later "simplifies" the schema, this fails and they have to argue the case.
    """
    from shared.models import AppConfig as Cfg

    names = {c.name for c in Cfg.__table__.columns}
    assert "content" not in names
    assert not any(c.type.__class__.__name__ == "LargeBinary" for c in Cfg.__table__.columns)


# --- the white-panel flag -------------------------------------------------
@pytest.mark.asyncio
async def test_the_plate_flag_has_its_own_endpoint(client):
    """Toggling a checkbox must not re-upload the image.

    The client used to re-fetch the stored logo and POST it back to change this
    one boolean, which sent a megabyte over the wire and — worse — re-ran
    validation on bytes whose filename had lost its extension, so a logo that
    uploaded fine could be rejected on a checkbox click.
    """
    headers = await _admin_headers(client)
    await client.post("/admin/branding/logo", **_upload(PNG, "l.png"), headers=headers)

    on = await client.patch(
        "/admin/branding/logo/light/plate",
        data={"needs_light_plate": "true"},
        headers=headers,
    )
    assert on.status_code == 200
    assert on.json()["logo_light_needs_plate"] is True

    off = await client.patch(
        "/admin/branding/logo/light/plate",
        data={"needs_light_plate": "false"},
        headers=headers,
    )
    assert off.json()["logo_light_needs_plate"] is False
    # The image itself is untouched: same bytes, same URL.
    assert off.json()["logo_light_url"] == on.json()["logo_light_url"]
    assert (await client.get("/auth/branding/logo/light")).content == PNG


@pytest.mark.asyncio
async def test_the_plate_endpoint_404s_with_no_logo(client):
    headers = await _admin_headers(client)
    r = await client.patch(
        "/admin/branding/logo/light/plate",
        data={"needs_light_plate": "true"},
        headers=headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_an_svg_with_a_long_preamble_is_still_recognised(client):
    """Exporters put licence comments and metadata before the root tag.

    The content sniff used to look only at the first 1024 bytes, so a file whose
    <svg> appeared after a long comment was refused unless its filename carried
    the extension.
    """
    headers = await _admin_headers(client)
    padded = (
        b'<?xml version="1.0"?>\n<!-- ' + b"x" * 1200 + b" -->\n"
        b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
    )
    r = await client.post(
        "/admin/branding/logo",
        files={"file": ("logo", padded, "application/octet-stream")},
        data={"variant": "light"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert b"M0 0" in (await client.get("/auth/branding/logo/light")).content
