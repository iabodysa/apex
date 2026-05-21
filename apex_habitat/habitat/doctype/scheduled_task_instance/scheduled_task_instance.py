"""Scheduled Task Instance controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class ScheduledTaskInstance(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Scheduled Task Instance":
            frappe.throw("DocType mismatch")


def validate(doc, method=None):
    if not doc.due_date:
        frappe.throw(_("Due Date is required."))


def on_submit(doc, method=None):
    doc.db_set("status", "Completed")


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is required before cancelling a Scheduled Task Instance."))
