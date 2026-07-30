"""Async Microsoft Graph client (app-only / client credentials).

Handles token acquisition via MSAL, ``@odata.nextLink`` paging, and Graph
throttling (honours ``429`` / ``Retry-After`` with exponential backoff). All
Graph field names stay Graph-native here; translation to the project's
Conversation/Prompt vocabulary happens in :mod:`worker.transforms`.
"""
from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx
import msal

logger = logging.getLogger("worker.graph")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_DEFAULT_SCOPE = ["https://graph.microsoft.com/.default"]
_MAX_RETRIES = 6
_MAX_BACKOFF_SECONDS = 60.0


class GraphError(RuntimeError):
    """Raised when Graph returns an unrecoverable error."""


class GraphAuthError(GraphError):
    """Raised when a client-credentials token cannot be acquired."""


class GraphAuth:
    """Acquires app-only Graph tokens using MSAL (with MSAL's token cache)."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        self._app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )

    async def token(self) -> str:
        """Return a valid access token (cached by MSAL between calls)."""
        result = await asyncio.to_thread(
            self._app.acquire_token_for_client, scopes=_DEFAULT_SCOPE
        )
        token = result.get("access_token")
        if not token:
            raise GraphAuthError(
                result.get("error_description")
                or result.get("error")
                or "token acquisition failed"
            )
        return token


class GraphClient:
    """Thin async wrapper over the Graph endpoints this project needs."""

    def __init__(
        self,
        auth: GraphAuth,
        *,
        concurrency: int = 15,
        timeout: float = 60.0,
    ) -> None:
        self._auth = auth
        self._client = httpx.AsyncClient(timeout=timeout)
        self._sem = asyncio.Semaphore(concurrency)

    async def __aenter__(self) -> "GraphClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def acquire_token(self) -> str:
        """Acquire an app-only token (used by connection tests)."""
        return await self._auth.token()

    # -- low-level -------------------------------------------------------
    async def _request(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """GET ``url`` with retry on 429/5xx, honouring ``Retry-After``."""
        for attempt in range(_MAX_RETRIES + 1):
            token = await self._auth.token()
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            async with self._sem:
                resp = await self._client.get(url, params=params, headers=headers)

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt >= _MAX_RETRIES:
                    resp.raise_for_status()
                delay = self._retry_delay(resp, attempt)
                logger.warning(
                    "Graph %s throttled/errored (attempt %d); retrying in %.1fs",
                    resp.status_code,
                    attempt + 1,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            if resp.status_code >= 400:
                raise GraphError(f"Graph {resp.status_code}: {resp.text[:500]}")
            return resp.json()
        raise GraphError("exhausted retries")  # pragma: no cover

    @staticmethod
    def _retry_delay(resp: httpx.Response, attempt: int) -> float:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return min(2.0**attempt, _MAX_BACKOFF_SECONDS) + random.random()

    async def _paged(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield items across all pages, following ``@odata.nextLink``."""
        next_url: str | None = url
        next_params = params
        while next_url:
            data = await self._request(next_url, params=next_params)
            for item in data.get("value", []):
                yield item
            next_url = data.get("@odata.nextLink")
            next_params = None  # nextLink already carries the query string

    # -- high-level endpoints -------------------------------------------
    async def iter_enterprise_interactions(
        self,
        user_id: str,
        since: datetime,
        until: datetime,
        *,
        page_size: int = 100,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield Copilot interactions for a user within ``[since, until)``."""
        url = (
            f"{GRAPH_BASE}/copilot/users/{user_id}"
            "/interactionHistory/getAllEnterpriseInteractions"
        )
        params = {
            "$filter": (
                f"createdDateTime gt {_iso(since)} "
                f"and createdDateTime lt {_iso(until)}"
            ),
            "$top": page_size,
        }
        async for item in self._paged(url, params=params):
            yield item

    async def iter_licensed_users(
        self, sku_ids: list[str]
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield users holding any of the configured Copilot SKUs."""
        clause = " or ".join(
            f"assignedLicenses/any(u:u/skuId eq {sku})" for sku in sku_ids
        )
        params = {
            "$select": "id,userPrincipalName,assignedLicenses",
            "$filter": clause,
        }
        async for item in self._paged(f"{GRAPH_BASE}/users", params=params):
            yield item

    async def get_subscribed_skus(self) -> list[dict[str, Any]]:
        """Return all subscribed SKUs (caller filters to Copilot)."""
        data = await self._request(f"{GRAPH_BASE}/subscribedSkus")
        return data.get("value", [])

    async def check_member_groups(
        self, user_id: str, group_ids: list[str]
    ) -> list[str]:
        """Return which of ``group_ids`` the user is a (transitive) member of.

        Uses the app-only ``checkMemberGroups`` action (needs Directory.Read.All,
        which the reporter already requires). Empty ``group_ids`` returns ``[]``.
        """
        if not group_ids:
            return []
        token = await self._auth.token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        url = f"{GRAPH_BASE}/users/{user_id}/checkMemberGroups"
        async with self._sem:
            resp = await self._client.post(
                url, headers=headers, json={"groupIds": group_ids}
            )
        if resp.status_code >= 400:
            raise GraphError(f"checkMemberGroups {resp.status_code}: {resp.text[:300]}")
        return list(resp.json().get("value", []))

    async def iter_directory_users(self) -> AsyncIterator[dict[str, Any]]:
        """Yield directory users with the fields needed for ``entra_users``."""
        params = {
            "$select": (
                "id,userPrincipalName,mail,userType,jobTitle,companyName,"
                "department,officeLocation,country,displayName,accountEnabled,"
                "assignedLicenses,onPremisesExtensionAttributes"
            ),
            "$expand": "manager($select=id)",
            "$top": 999,
        }
        async for item in self._paged(f"{GRAPH_BASE}/users", params=params):
            yield item

    async def get_manager_id(self, user_id: str) -> str | None:
        """Return the user's manager id, or ``None`` if unset."""
        url = f"{GRAPH_BASE}/users/{user_id}"
        try:
            data = await self._request(
                url, params={"$select": "id", "$expand": "manager($select=id)"}
            )
        except GraphError:
            return None
        return (data.get("manager") or {}).get("id")


def _iso(value: datetime) -> str:
    """Format a datetime as an ISO-8601 string Graph accepts (UTC ``Z``)."""
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")
