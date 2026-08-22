# Copyright (c) 2026, afmcoltd
"""What a building's derived capacity and cost figures are computed FROM.

The arithmetic here takes plain numbers and returns numbers, so the rent
annualisation and the cost-per-capacity rules can be exercised without a bench.
``ANNUAL_COST_FIELDS`` is the one list of cost columns: the total and the rollup trigger
set both read it, so adding a cost column is one edit. Refusing a negative is NOT here —
each column carries ``non_negative`` in the DocType JSON, which frappe enforces in
``Document._validate_non_negative`` after ``before_save``, so the derived value is what
gets tested rather than the stored one.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt

LEASE_CYCLE_FACTOR = {"Monthly": 12, "Quarterly": 4, "Semi-Annual": 2, "Annual": 1}

ANNUAL_COST_FIELDS = (
    "annual_rent",
    "annual_electricity",
    "annual_water",
    "annual_cleaning_staff",
    "annual_supervision",
    "annual_other_expenses",
)

ROLLUP_TRIGGER_FIELDS = ANNUAL_COST_FIELDS + ("total_capacity", "landlord")


def annualized_rent(rent_amount, billing_cycle, company_share_pct) -> float:
    """A lease's rent as an annual figure, then narrowed to the company's share.

    An unrecognised billing cycle is treated as already annual. A zero or unset
    share means the whole rent is the company's, not that nothing is owed."""
    annual = flt(rent_amount) * LEASE_CYCLE_FACTOR.get(billing_cycle, 1)
    if flt(company_share_pct):
        annual = annual * flt(company_share_pct) / 100.0
    return annual


def total_annual_cost(source) -> float:
    """Sum of every annual cost column on a building (or any mapping of them)."""
    total = 0
    for field in ANNUAL_COST_FIELDS:
        total += source.get(field) or 0
    return total


def cost_per_capacity(annual_total, capacity):
    """``(annual, monthly)`` cost per head. A building with no capacity costs
    nothing per head rather than dividing by zero."""
    if not capacity:
        return 0, 0
    annual = annual_total / capacity
    return annual, annual / 12


def derive_total_capacity(building_name):
    """Count the building's real beds, excluding Out-of-Service and virtual
    ``is_temporary`` over-capacity beds. ``None`` when it has no bed rows yet (the
    pre-generation path — keep the manually-entered planned figure); 0 when it has
    beds but all are excluded.
    """
    if not frappe.db.exists("Bed", {"building": building_name}):
        return None
    return frappe.db.count(
        "Bed",
        {
            "building": building_name,
            "status": ["!=", "Out of Service"],
            "is_temporary": 0,
        },
    )


def distinct_floor_count(building_name) -> int:
    """How many floors the building's rooms occupy, counting the ground floor as one.

    A Room's ``floor`` is a Frappe ``Int``, whose column is ``int(11) NOT NULL DEFAULT 0``, so a
    room whose floor was never set is stored as 0 and is indistinguishable from a room on the
    ground floor. This deliberately does NOT try to tell them apart: the previous version filtered
    ``f is not None`` and promised "rooms with no floor set are not a floor", which the schema
    cannot express — the filter could never fire, and the promise read as a guarantee nobody held.
    Rooms are generated from the building's floor plan with an explicit floor, so an unset floor is
    not a state the product produces.
    """
    return len(
        frappe.db.get_all(
            "Room", filters={"building": building_name}, pluck="floor", distinct=True
        )
    )
