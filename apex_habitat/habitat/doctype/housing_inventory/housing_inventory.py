# Copyright (c) 2026, AFMCO and contributors
"""Housing Inventory controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate


class HousingInventory(Document):
    def before_save(self):
        # Variance is derived, never hand-entered, so the count and any report agree.
        self.quantity_variance = flt(self.counted_quantity) - flt(self.expected_quantity)
        # Stamp the count date on the first count AND whenever the counted quantity
        # is recorded again (a field re-count via the portal must advance the date).
        if self.counted_quantity is not None and (
            self.last_count_date is None or self.has_value_changed("counted_quantity")
        ):
            self.last_count_date = getdate()


def reflect_completed_maintenance(doc, method=None):
    """Reflect a completed Maintenance Work Order onto the housing item that links its asset.

    Call from the Work Order completion chokepoint (mark_completed): completion sets
    status via db_set, which fires no on_update doc_event, so a hooks wiring would not
    catch it. The Work Order reaches its asset through the Maintenance Request's
    related_facility_asset; every Housing Inventory row whose linked_facility_asset
    matches gets its maintenance stamps advanced. Idempotent and order-safe: only
    advance last_maintenance_date (never roll it back) and clear a maintenance
    condition/status, so a re-run or an out-of-order completion leaves the latest.
    """
    if doc.status != "Completed" or not doc.maintenance_request:
        return
    asset = frappe.db.get_value(
        "Maintenance Request", doc.maintenance_request, "related_facility_asset"
    )
    if not asset:
        return
    completion_date = getdate(doc.actual_end_date) if doc.actual_end_date else getdate()
    for name in frappe.get_all(
        "Housing Inventory", filters={"linked_facility_asset": asset}, pluck="name"
    ):
        row = frappe.get_doc("Housing Inventory", name)
        if row.last_maintenance_date and getdate(row.last_maintenance_date) >= completion_date:
            continue
        row.db_set("last_maintenance_date", completion_date)
        row.db_set("last_maintenance_work_order", doc.name)
        row.db_set("maintenance_count", (row.maintenance_count or 0) + 1)
        if row.condition == "Needs Maintenance":
            row.db_set("condition", "Good")
        if row.status == "Under Maintenance":
            row.db_set("status", "Active")
