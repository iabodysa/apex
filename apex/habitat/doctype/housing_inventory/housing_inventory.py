# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate


class HousingInventory(Document):
    def before_save(self):
        self.quantity_variance = flt(self.counted_quantity) - flt(self.expected_quantity)
        if self.counted_quantity is not None and (
            self.last_count_date is None or self.has_value_changed("counted_quantity")
        ):
            self.last_count_date = getdate()


def reflect_completed_maintenance(doc, method=None):
    if doc.status != "Completed" or not doc.maintenance_request:
        return
    asset = frappe.db.get_value(
        "Maintenance Request", doc.maintenance_request, "related_facility_asset"
    )
    if not asset:
        return
    completion_date = getdate(doc.actual_end_date) if doc.actual_end_date else getdate()
    for name in frappe.get_all(
        "Housing Inventory", filters={"facility_asset": asset}, pluck="name"
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
