# Copyright (c) 2026, AFMCO and contributors
"""Top Workers by Custody Value — chart source over the Accommodation Stock Ledger.

Reuses the canonical outstanding-custody-value definition (net signed
qty * unit_cost over non-cancelled Custody Article rows with an employee set)
shared by the value-in-hands Number Card and the Outstanding-by-Worker report,
grouped per employee and capped at the top holders by value.
"""

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.dashboard import cache_source

from apex.habitat.api.dashboard import get_top_custody_holders_by_value


@frappe.whitelist()
@cache_source
def get(
    chart_name=None,
    chart=None,
    no_cache=None,
    filters=None,
    from_date=None,
    to_date=None,
    timespan=None,
    time_interval=None,
    heatmap_year=None,
):
    frappe.has_permission("Accommodation Stock Ledger", "read", throw=True)
    rows = get_top_custody_holders_by_value(limit=10)
    if not rows:
        return {"labels": [], "datasets": [{"name": _("Custody Value (SAR)"), "values": []}], "type": "bar"}

    employees = [r["employee"] for r in rows]
    name_map = dict(
        frappe.get_all(
            "Employee",
            filters={"name": ["in", employees]},
            fields=["name", "employee_name"],
            as_list=True,
        )
    )

    return {
        "labels": [name_map.get(r["employee"]) or r["employee"] for r in rows],
        "datasets": [{"name": _("Custody Value (SAR)"), "values": [flt(r["value"]) for r in rows]}],
        "type": "bar",
    }
