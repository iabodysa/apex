"""Maintenance Inspection Report controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class MaintenanceInspectionReport(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Maintenance Inspection Report":
            frappe.throw("DocType mismatch")


def validate(doc, method=None):
    if not doc.findings:
        frappe.throw(_("At least one finding is required on a Maintenance Inspection Report."))


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is required before cancelling a Maintenance Inspection Report."))
