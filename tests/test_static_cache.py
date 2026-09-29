"""Cache headers on the served SPA.

The bug these pin: index.html was served with no cache directive at all, so a
browser applied its own heuristic and kept serving the bundle it already had.
An upgraded deployment then looked, from the outside, exactly like a deploy
that had silently failed — the server had the new code and said so, and the
browser went on asking for the old one.

Vite content-hashes asset filenames, so the split is: assets may be cached
forever because their URL changes when their contents do; index.html must
revalidate every time because its URL never changes and its contents do.
"""
from __future__ import annotations

import os

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager


@pytest_asyncio.fixture
async def client(tmp_path_factory, monkeypatch):
    """An app with a fake built bundle mounted, as production has."""
    dist = tmp_path_factory.mktemp("dist")
    (dist / "index.html").write_text("<!doctype html><title>app</title>")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "index-abc123.js").write_text("console.log(1)")
    (dist / "favicon.png").write_bytes(b"\x89PNG")

    monkeypatch.setenv("FRONTEND_DIST", str(dist))
    # The mount is decided at import time, so the module has to be (re)imported
    # with the setting in place.
    import importlib

    from shared import config as config_module

    config_module.settings.frontend_dist = str(dist)
    import api.main as main_module

    importlib.reload(main_module)

    async with LifespanManager(main_module.app):
        transport = httpx.ASGITransport(app=main_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.mark.asyncio
async def test_hashed_assets_are_cached_forever(client):
    r = await client.get("/assets/index-abc123.js")
    assert r.status_code == 200
    cache = r.headers.get("cache-control", "")
    assert "immutable" in cache
    assert "max-age=31536000" in cache


@pytest.mark.asyncio
async def test_index_html_always_revalidates(client):
    """The one that matters: the entry point must never be held by a browser."""
    r = await client.get("/")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-cache"


@pytest.mark.asyncio
async def test_a_deep_link_also_revalidates(client):
    """Deep links fall back to index.html and must not be cached either."""
    r = await client.get("/settings")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-cache"


@pytest.mark.asyncio
async def test_unhashed_root_files_revalidate(client):
    """favicon and logos keep their names across releases, so a refreshed one
    has to be able to arrive."""
    r = await client.get("/favicon.png")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-cache"
