# Copyright (c) 2026, afmcoltd

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
    annual = flt(rent_amount) * LEASE_CYCLE_FACTOR.get(billing_cycle, 1)
    if flt(company_share_pct):
        annual = annual * flt(company_share_pct) / 100.0
    return annual


def total_annual_cost(source) -> float:
    total = 0
    for field in ANNUAL_COST_FIELDS:
        total += source.get(field) or 0
    return total


def cost_per_capacity(annual_total, capacity):
    if not capacity:
        return 0, 0
    annual = annual_total / capacity
    return annual, annual / 12


def derive_total_capacity(building_name):
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
    return len(
        frappe.db.get_all(
            "Room", filters={"building": building_name}, pluck="floor", distinct=True
        )
    )
