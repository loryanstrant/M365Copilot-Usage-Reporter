"""Customer branding: read it publicly, change it as an admin.

See docs/specs/customer-branding.md. A customer's logo and accent colour are
*added* to the product's own marks, never substituted for them.

**Why the public routes live under ``/auth``.** The sign-in screen has to be
branded, so the read has to work before there is a user. ``/auth`` is already
the established "reachable before sign-in" surface (see ``/auth/config``), and
— the practical reason — ``frontend/vite.config.ts`` proxies only ``/auth``,
``/admin``, ``/metrics`` and ``/health``. A top-level ``/branding`` prefix would
work in the container and silently return ``index.html`` under ``npm run dev``,
which is the worst way for a route to be wrong.

Both routers must be registered in ``_register_routers()``, which runs *before*
``_mount_frontend()``. Registered after it, every URL here would be swallowed by
the SPA catch-all and return HTML with a 200.
"""
from __future__ import annotations

import hashlib
import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi import status as http_status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import CurrentUser, require_admin
from api.schemas import (
    BrandingAdminOut,
    BrandingIn,
    BrandingOut,
    RampPreviewIn,
    RampPreviewOut,
)
from shared.branding import BrandingError, derive_ramps, normalise_hex
from shared.db import get_session
from shared.models import AppConfig, BrandingAsset
from shared.svg_safe import UnsafeSvgError, sanitise_svg

logger = logging.getLogger("api.branding")

public_router = APIRouter(prefix="/auth/branding", tags=["branding"])
admin_router = APIRouter(
    prefix="/admin/branding",
    tags=["branding"],
    dependencies=[Depends(require_admin)],
)

MAX_LOGO_BYTES = 1024 * 1024
VARIANTS = ("light", "dark")

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"

LOGO_HEADERS = {
    # These bytes came from an upload. In the app a logo is only ever loaded
    # through an <img> tag, where no browser runs SVG script — this is the lock
    # for someone who opens the URL directly. Applied to this response only:
    # an app-wide policy would break the SPA's inline styles and Vite's module
    # scripts, and is separate, larger work.
    "Content-Security-Policy": (
        "default-src 'none'; img-src data:; style-src 'unsafe-inline'; sandbox"
    ),
    "X-Content-Type-Options": "nosniff",
    "Content-Disposition": "inline",
    # Not under /assets, so the immutable mount and its tests are untouched.
    # Short max-age plus a strong ETag: a replacement is picked up at once via
    # the ?v= in the URL, and a client holding a stale copy heals in minutes
    # rather than never.
    "Cache-Control": "public, max-age=300, must-revalidate",
}


# --- helpers --------------------------------------------------------------
async def _get_config(session: AsyncSession) -> AppConfig | None:
    return await session.get(AppConfig, 1)


async def _get_assets(session: AsyncSession) -> dict[str, BrandingAsset]:
    rows = (await session.execute(select(BrandingAsset))).scalars().all()
    return {row.variant: row for row in rows}


def _to_out(
    cfg: AppConfig | None,
    assets: dict[str, BrandingAsset],
    *,
    admin: bool = False,
) -> BrandingOut:
    """Build every branding response through one place, so shapes can't drift."""
    light_asset = assets.get("light")
    dark_asset = assets.get("dark")

    payload: dict[str, object] = {
        "org_display_name": cfg.org_display_name if cfg else None,
        "brand_primary_hex": cfg.brand_primary_hex if cfg else None,
        "has_logo_light": light_asset is not None,
        "has_logo_dark": dark_asset is not None,
        "logo_light_url": (
            f"/auth/branding/logo/light?v={light_asset.etag}" if light_asset else None
        ),
        "logo_dark_url": (
            f"/auth/branding/logo/dark?v={dark_asset.etag}" if dark_asset else None
        ),
        "logo_light_needs_plate": bool(light_asset and light_asset.needs_light_plate),
    }

    seed = cfg.brand_primary_hex if cfg else None
    if seed:
        try:
            brand = derive_ramps(seed)
        except BrandingError:
            # A colour that cannot be derived should not take the app down. Log
            # it and serve an unbranded palette; the admin can re-save.
            logger.warning("stored brand colour %r is unusable; ignoring", seed)
        else:
            light, dark = brand.as_json_ramps()
            payload.update(
                ramp_light=light,
                ramp_dark=dark,
                dark_accent_lifted=brand.dark_accent_lifted,
                dark_accent_contrast=round(brand.dark_accent_contrast, 2),
                gradient_needs_deepening=brand.gradient_needs_deepening,
            )

    if not admin:
        return BrandingOut(**payload)  # type: ignore[arg-type]

    return BrandingAdminOut(
        **payload,  # type: ignore[arg-type]
        logo_light_bytes=light_asset.byte_size if light_asset else None,
        logo_dark_bytes=dark_asset.byte_size if dark_asset else None,
        updated_at=cfg.updated_at if cfg else None,
        updated_by=cfg.updated_by if cfg else None,
    )


def _check_variant(variant: str) -> str:
    if variant not in VARIANTS:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Unknown logo slot.")
    return variant


def _validate_image(filename: str, content: bytes) -> tuple[bytes, str]:
    """Return (bytes to store, mime), rejecting anything we will not serve.

    The MIME comes from what the bytes actually are and from the sanitiser's
    verdict — never from the client's Content-Type, which is a claim rather
    than a fact.
    """
    if content.startswith(_PNG_MAGIC):
        return content, "image/png"
    if content.startswith(_JPEG_MAGIC):
        return content, "image/jpeg"

    looks_like_svg = filename.lower().endswith(".svg") or b"<svg" in content[:1024]
    if looks_like_svg:
        try:
            return sanitise_svg(content), "image/svg+xml"
        except UnsafeSvgError as exc:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    raise HTTPException(
        http_status.HTTP_400_BAD_REQUEST,
        "That file doesn't look like a PNG, JPEG or SVG image. "
        "Please re-export it and try again.",
    )


# --- public ---------------------------------------------------------------
@public_router.get("", response_model=BrandingOut)
async def get_branding(session: AsyncSession = Depends(get_session)) -> BrandingOut:
    """Branding for the SPA. Public: the sign-in screen needs it."""
    return _to_out(await _get_config(session), await _get_assets(session))


@public_router.get("/logo/{variant}")
async def get_logo(
    variant: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Serve one logo. Public, for the same reason as the payload above."""
    _check_variant(variant)
    # Select only this row: never load both images to serve one.
    asset = (
        await session.execute(
            select(BrandingAsset).where(BrandingAsset.variant == variant)
        )
    ).scalar_one_or_none()
    if asset is None:
        # A JSON 404, explicitly — not the SPA's index.html, which is what a
        # route registered on the wrong side of the catch-all would return.
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "No logo has been set.")

    etag = f'"{asset.etag}"'
    headers = {**LOGO_HEADERS, "ETag": etag}
    # A conditional request may carry several ETags, or `*`.
    if_none_match = request.headers.get("if-none-match", "")
    if if_none_match and (
        if_none_match.strip() == "*"
        or etag in {candidate.strip() for candidate in if_none_match.split(",")}
    ):
        return Response(status_code=http_status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=asset.content, media_type=asset.mime, headers=headers)


# --- admin ----------------------------------------------------------------
@admin_router.get("", response_model=BrandingAdminOut)
async def get_branding_admin(
    session: AsyncSession = Depends(get_session),
) -> BrandingOut:
    return _to_out(
        await _get_config(session), await _get_assets(session), admin=True
    )


@admin_router.put("", response_model=BrandingAdminOut)
async def put_branding(
    body: BrandingIn,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> BrandingOut:
    cfg = await _get_config(session)
    if cfg is None:
        cfg = AppConfig(id=1)
        session.add(cfg)

    if body.org_display_name is not None:
        cfg.org_display_name = body.org_display_name.strip() or None
    if body.brand_primary_hex is not None:
        raw = body.brand_primary_hex.strip()
        if not raw:
            cfg.brand_primary_hex = None
        else:
            try:
                cfg.brand_primary_hex = normalise_hex(raw)
            except BrandingError as exc:
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST, str(exc)
                ) from exc
    cfg.updated_by = user.username

    await session.commit()
    await session.refresh(cfg)
    return _to_out(cfg, await _get_assets(session), admin=True)


@admin_router.post("/logo", response_model=BrandingAdminOut)
async def upload_logo(
    file: UploadFile = File(...),
    variant: str = Form("light"),
    needs_light_plate: bool = Form(False),
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> BrandingOut:
    _check_variant(variant)

    # Bounded read. `await file.read()` with no argument buffers the whole
    # upload before we can refuse it, so a 500 MB POST would be accepted into
    # memory and only then rejected. Reading one byte past the cap is enough to
    # know it is over.
    content = await file.read(MAX_LOGO_BYTES + 1)
    if len(content) > MAX_LOGO_BYTES:
        raise HTTPException(
            http_status.HTTP_413_CONTENT_TOO_LARGE,
            "That file is larger than 1 MB. Please choose a smaller image.",
        )
    if not content:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST, "That file is empty."
        )

    stored, mime = _validate_image(file.filename or "", content)
    etag = hashlib.sha256(stored).hexdigest()[:16]

    asset = (
        await session.execute(
            select(BrandingAsset).where(BrandingAsset.variant == variant)
        )
    ).scalar_one_or_none()
    if asset is None:
        asset = BrandingAsset(variant=variant)
        session.add(asset)
    asset.mime = mime
    asset.content = stored
    asset.etag = etag
    asset.byte_size = len(stored)
    asset.needs_light_plate = bool(needs_light_plate)
    asset.updated_by = user.username

    await session.commit()
    return _to_out(
        await _get_config(session), await _get_assets(session), admin=True
    )


@admin_router.delete("/logo/{variant}", response_model=BrandingAdminOut)
async def delete_logo(
    variant: str, session: AsyncSession = Depends(get_session)
) -> BrandingOut:
    _check_variant(variant)
    await session.execute(
        delete(BrandingAsset).where(BrandingAsset.variant == variant)
    )
    await session.commit()
    return _to_out(
        await _get_config(session), await _get_assets(session), admin=True
    )


@admin_router.post("/preview", response_model=RampPreviewOut)
async def preview_ramp(body: RampPreviewIn) -> RampPreviewOut:
    """Derive a ramp without saving it, for the live Settings preview.

    Deriving server-side keeps the colour maths in exactly one implementation.
    A second copy in TypeScript would drift, and the drift would show up as the
    preview disagreeing with the saved result — the single most confusing way
    for this feature to break.
    """
    try:
        brand = derive_ramps(body.brand_primary_hex)
    except BrandingError as exc:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    light, dark = brand.as_json_ramps()
    return RampPreviewOut(
        ramp_light=light,
        ramp_dark=dark,
        light_accent_contrast=round(brand.light_accent_contrast, 2),
        dark_accent_contrast=round(brand.dark_accent_contrast, 2),
        dark_accent_lifted=brand.dark_accent_lifted,
        gradient_needs_deepening=brand.gradient_needs_deepening,
    )


@admin_router.delete("", response_model=BrandingAdminOut)
async def reset_branding(
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> BrandingOut:
    """Remove the name, the colour and both logos — back to the product look."""
    cfg = await _get_config(session)
    await session.execute(delete(BrandingAsset))
    if cfg is None:
        await session.commit()
        return _to_out(None, {}, admin=True)

    cfg.org_display_name = None
    cfg.brand_primary_hex = None
    cfg.updated_by = user.username
    await session.commit()
    # Refresh explicitly rather than re-fetching: commit expires the instance,
    # and reading an attribute off an expired object outside the async context
    # raises MissingGreenlet instead of lazily loading.
    await session.refresh(cfg)
    return _to_out(cfg, {}, admin=True)
