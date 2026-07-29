"""Health endpoint test using an ASGI transport (no network)."""
from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager

from api.main import app


@pytest.mark.asyncio
async def test_health_ok():
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] is True
