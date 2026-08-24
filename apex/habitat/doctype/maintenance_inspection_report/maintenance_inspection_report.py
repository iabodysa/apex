# Copyright (c) 2026, afmcoltd
"""Maintenance Inspection Report controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class MaintenanceInspectionReport(Document):

    def on_submit(self):
        """Stamp the inspected Facility Asset's last_inspection_date.

        Keep the most recent date: only advance the stamp, never roll it back, so
        reports submitted out of date order still leave the latest date on the asset.
        """
        if not self.facility_asset or not self.inspection_date:
            return
        current = frappe.db.get_value("Facility Asset", self.facility_asset, "last_inspection_date")
        if not current or getdate(self.inspection_date) > getdate(current):
            frappe.db.set_value(
                "Facility Asset", self.facility_asset, "last_inspection_date", self.inspection_date
            )

    def on_cancel(self):
        """Recompute the asset stamp from the remaining submitted inspections.

        A plain revert is unsafe (this may not be the report that set the date), so
        re-derive last_inspection_date as the max over still-submitted reports.
        """
        if not self.facility_asset:
            return
        remaining = frappe.get_all(
            "Maintenance Inspection Report",
            filters={"facility_asset": self.facility_asset, "docstatus": 1, "name": ("!=", self.name)},
            fields=["inspection_date"],
            order_by="inspection_date desc",
            limit=1,
        )
        latest = remaining[0].inspection_date if remaining else None
        frappe.db.set_value("Facility Asset", self.facility_asset, "last_inspection_date", latest)


def before_cancel(doc, method=None):
    """Blocks cancelling a Maintenance Inspection Report without a stated cancellation reason."""
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is required before cancelling a Maintenance Inspection Report."))
