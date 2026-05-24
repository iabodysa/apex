"""On-form dashboard metrics for the Accommodation Building form.

Frappe's form `get_data()` only renders the links/transactions section; the
occupancy chart and indicator counts at the top of the form are rendered
client-side (accommodation_building.js) from this whitelisted reader.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_building_metrics(building: str) -> dict:
    frappe.has_permission("Accommodation Building", "read", doc=building, throw=True)

    snaps = frappe.get_all(
        "Accommodation Occupancy Snapshot",
        filters={"building": building},
        fields=["snapshot_date", "occupancy_percent"],
        order_by="snapshot_date asc",
        limit_page_length=60,
    )
    return {
        "labels": [str(s.snapshot_date) for s in snaps],
        "occupancy": [flt(s.occupancy_percent) for s in snaps],
        "active_occupants": frappe.db.count(
            "Accommodation Assignment",
            {"building": building, "docstatus": 1, "check_out_date": ["is", "not set"]},
        ),
        "open_maintenance": frappe.db.count(
            "Maintenance Request",
            {"building": building, "status": ["not in", ["Closed", "Cancelled", "Resolved"]]},
        ),
        "open_custody": frappe.db.count(
            "Custody Issue",
            {"building": building, "docstatus": 1, "status": ["in", ["Issued", "Partially Returned"]]},
        ),
    }
