"""Deciding who holds a Microsoft 365 Copilot licence.

Copilot is not one SKU. It ships inside several — Microsoft 365 Copilot (under
two different SKU IDs), Microsoft 365 E7, Copilot for Sales and the education
faculty SKU — and Microsoft adds more over time. Naming them individually is a
list that is wrong the day it is written: this app shipped with one of them,
so E7 users were invisible and so were holders of the second Copilot SKU.

What every Copilot-bearing SKU has in common is the service plan **"Microsoft
Copilot with Graph-grounded chat"** (``M365_COPILOT_BUSINESS_CHAT``). So
rather than matching SKU IDs, we ask the tenant which of *its* subscriptions
contain that plan, and match those.

The service plan also settles a second question the SKU list could not answer.
A bundle can be assigned with parts switched off, so an E7 user may hold the
SKU with Copilot disabled. Graph reports that per assignment in
``disabledPlans``, and someone with the plan disabled is not licensed however
the SKU is counted.
"""
from __future__ import annotations

from typing import Any, Iterable

# Service plan "Microsoft Copilot with Graph-grounded chat"
# (M365_COPILOT_BUSINESS_CHAT). Source: Microsoft's published product names and
# service plan identifiers for licensing.
COPILOT_SERVICE_PLAN_ID = "3f30311c-6b1e-48a4-ab79-725b469da960"

# Only used to explain an empty result to an administrator; detection never
# reads this list.
KNOWN_COPILOT_SKUS = {
    "639dec6b-bb19-468b-871c-c5c441c4b0cb": "Microsoft 365 Copilot",
    "a809996b-059e-42e2-9866-db24b99a9782": "Microsoft 365 Copilot",
    "9a18296a-025f-4e37-9ffa-30bf8d1ce775": "Microsoft 365 E7",
    "15f2e9fc-b782-4f73-bf51-81d8b7fff6f4": "Microsoft 365 Copilot for Sales",
    "ad9c22b3-52d7-4e7e-973c-88121ea96436": "Microsoft 365 Copilot (Education Faculty)",
}


def sku_grants_copilot(sku: dict[str, Any]) -> bool:
    """True when a ``subscribedSkus`` entry contains Graph-grounded chat."""
    for plan in sku.get("servicePlans") or []:
        if plan.get("servicePlanId") == COPILOT_SERVICE_PLAN_ID:
            return True
    return False


def copilot_granting_skus(
    subscribed_skus: Iterable[dict[str, Any]],
    *,
    override: Iterable[str] | None = None,
) -> set[str]:
    """The tenant's SKU IDs that grant Copilot.

    ``override`` is the administrator's manual list. It is only for tenants
    where detection gets it wrong; an empty or missing override means detect.
    """
    manual = {s.strip() for s in (override or []) if s and s.strip()}
    if manual:
        return manual
    return {
        sku["skuId"]
        for sku in subscribed_skus
        if sku.get("skuId") and sku_grants_copilot(sku)
    }


def has_copilot_license(user: dict[str, Any], granting_skus: Iterable[str]) -> bool:
    """True when the user holds a granting SKU with Copilot still switched on.

    A bundle assigned with Copilot in ``disabledPlans`` does not count, which is
    the case a SKU-only check gets wrong.
    """
    wanted = set(granting_skus)
    for lic in user.get("assignedLicenses") or []:
        if lic.get("skuId") not in wanted:
            continue
        if COPILOT_SERVICE_PLAN_ID in set(lic.get("disabledPlans") or []):
            continue
        return True
    return False


def describe_granting_skus(
    subscribed_skus: Iterable[dict[str, Any]],
    granting: Iterable[str],
) -> list[dict[str, Any]]:
    """Summarise, for the Settings screen, which subscriptions were matched.

    Every subscription is returned with whether it counts, so an administrator
    can see that a SKU was considered and rejected rather than overlooked.
    """
    counted = set(granting)
    out: list[dict[str, Any]] = []
    for sku in subscribed_skus:
        sku_id = sku.get("skuId")
        if not sku_id:
            continue
        prepaid = sku.get("prepaidUnits") or {}
        out.append(
            {
                "sku_id": sku_id,
                "name": KNOWN_COPILOT_SKUS.get(sku_id)
                or sku.get("skuPartNumber")
                or sku_id,
                "grants_copilot": sku_id in counted,
                "seats": int(prepaid.get("enabled") or 0),
                "assigned": int(sku.get("consumedUnits") or 0),
            }
        )
    # Counted subscriptions first, then biggest, so the ones that matter lead.
    out.sort(key=lambda r: (not r["grants_copilot"], -r["seats"]))
    return out


__all__ = [
    "COPILOT_SERVICE_PLAN_ID",
    "KNOWN_COPILOT_SKUS",
    "copilot_granting_skus",
    "describe_granting_skus",
    "has_copilot_license",
    "sku_grants_copilot",
]
