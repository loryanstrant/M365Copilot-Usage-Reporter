"""Copilot licence detection.

The bug this replaces: detection matched a configured list of SKU IDs, shipped
containing only the Microsoft 365 Copilot SKU. E7 bundles Copilot, so every E7
user was invisible — and so was everyone on the second Microsoft 365 Copilot
SKU, which nobody had noticed existed.

Detection now matches the "Microsoft Copilot with Graph-grounded chat" service
plan, which every Copilot-bearing SKU contains, and honours disabledPlans so a
bundle with Copilot switched off does not count.
"""
from __future__ import annotations

from worker.licensing import (
    COPILOT_SERVICE_PLAN_ID,
    copilot_granting_skus,
    describe_granting_skus,
    has_copilot_license,
    sku_grants_copilot,
)

COPILOT = "639dec6b-bb19-468b-871c-c5c441c4b0cb"
COPILOT_SECOND = "a809996b-059e-42e2-9866-db24b99a9782"
E7 = "9a18296a-025f-4e37-9ffa-30bf8d1ce775"
E5 = "06ebc4ee-1bb5-47dd-8120-11324bc54e06"

OTHER_PLAN = "11111111-1111-1111-1111-111111111111"


def _sku(sku_id: str, *, copilot: bool, name: str = "SKU", seats: int = 100):
    plans = [{"servicePlanId": OTHER_PLAN, "servicePlanName": "EXCHANGE"}]
    if copilot:
        plans.append(
            {
                "servicePlanId": COPILOT_SERVICE_PLAN_ID,
                "servicePlanName": "M365_COPILOT_BUSINESS_CHAT",
            }
        )
    return {
        "skuId": sku_id,
        "skuPartNumber": name,
        "servicePlans": plans,
        "prepaidUnits": {"enabled": seats},
        "consumedUnits": seats // 2,
    }


def _user(*licenses):
    return {"id": "u1", "assignedLicenses": list(licenses)}


def _assigned(sku_id: str, *, disabled: list[str] | None = None):
    return {"skuId": sku_id, "disabledPlans": disabled or []}


TENANT = [
    _sku(COPILOT, copilot=True, name="Microsoft_365_Copilot"),
    _sku(E7, copilot=True, name="MICROSOFT_365_E7", seats=340),
    _sku(E5, copilot=False, name="SPE_E5", seats=2000),
]


# --------------------------------------------------------------------------- #
# Which SKUs grant Copilot
# --------------------------------------------------------------------------- #
def test_a_sku_grants_copilot_when_it_carries_graph_grounded_chat():
    assert sku_grants_copilot(_sku(E7, copilot=True)) is True
    assert sku_grants_copilot(_sku(E5, copilot=False)) is False


def test_e7_is_detected_without_being_configured():
    """The whole point: nobody typed E7's GUID anywhere."""
    granting = copilot_granting_skus(TENANT)
    assert E7 in granting
    assert COPILOT in granting
    assert E5 not in granting


def test_a_second_copilot_sku_is_picked_up_too():
    tenant = TENANT + [_sku(COPILOT_SECOND, copilot=True)]
    assert COPILOT_SECOND in copilot_granting_skus(tenant)


def test_an_unknown_future_sku_is_picked_up_by_its_service_plan():
    """Detection must not depend on recognising the SKU ID."""
    future = _sku("00000000-0000-0000-0000-00000000ffff", copilot=True)
    assert "00000000-0000-0000-0000-00000000ffff" in copilot_granting_skus(
        TENANT + [future]
    )


def test_a_manual_override_wins():
    """An administrator can force the answer in an odd tenant."""
    assert copilot_granting_skus(TENANT, override=[E5]) == {E5}
    # Blank entries are not an override.
    assert copilot_granting_skus(TENANT, override=["", "  "]) == {COPILOT, E7}


# --------------------------------------------------------------------------- #
# Who holds one
# --------------------------------------------------------------------------- #
def test_an_e7_holder_counts_as_licensed():
    granting = copilot_granting_skus(TENANT)
    assert has_copilot_license(_user(_assigned(E7)), granting) is True


def test_an_e7_holder_with_copilot_switched_off_does_not_count():
    """The case a SKU-only check gets wrong."""
    granting = copilot_granting_skus(TENANT)
    user = _user(_assigned(E7, disabled=[COPILOT_SERVICE_PLAN_ID]))
    assert has_copilot_license(user, granting) is False


def test_another_disabled_plan_does_not_remove_the_licence():
    granting = copilot_granting_skus(TENANT)
    user = _user(_assigned(E7, disabled=[OTHER_PLAN]))
    assert has_copilot_license(user, granting) is True


def test_a_second_licence_can_still_grant_it():
    """Copilot disabled in the bundle, but a standalone SKU also assigned."""
    granting = copilot_granting_skus(TENANT)
    user = _user(
        _assigned(E7, disabled=[COPILOT_SERVICE_PLAN_ID]),
        _assigned(COPILOT),
    )
    assert has_copilot_license(user, granting) is True


def test_an_e5_only_user_is_not_licensed():
    granting = copilot_granting_skus(TENANT)
    assert has_copilot_license(_user(_assigned(E5)), granting) is False


def test_a_user_with_no_licences_is_not_licensed():
    assert has_copilot_license({"id": "u"}, copilot_granting_skus(TENANT)) is False


# --------------------------------------------------------------------------- #
# What Settings shows
# --------------------------------------------------------------------------- #
def test_every_subscription_is_listed_with_whether_it_counts():
    granting = copilot_granting_skus(TENANT)
    rows = describe_granting_skus(TENANT, granting)
    by_id = {r["sku_id"]: r for r in rows}
    assert by_id[E7]["grants_copilot"] is True
    # E5 is shown, but marked as not counted, so it reads as considered and
    # rejected rather than missed.
    assert by_id[E5]["grants_copilot"] is False
    assert by_id[E7]["seats"] == 340
    # Counted subscriptions lead.
    assert rows[0]["grants_copilot"] is True
    assert rows[-1]["sku_id"] == E5


def test_a_known_sku_gets_a_readable_name():
    rows = describe_granting_skus(TENANT, copilot_granting_skus(TENANT))
    assert {r["sku_id"]: r["name"] for r in rows}[E7] == "Microsoft 365 E7"


# --------------------------------------------------------------------------- #
# A tenant that owns no Copilot subscription
# --------------------------------------------------------------------------- #
def test_a_tenant_with_no_copilot_subscription_grants_nothing():
    assert copilot_granting_skus([_sku(E5, copilot=False)]) == set()
    assert copilot_granting_skus([]) == set()
