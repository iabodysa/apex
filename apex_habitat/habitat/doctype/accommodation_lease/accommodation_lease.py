"""Accommodation Lease controller.

Thin DocType: lease contract period + rent payment schedule.
Landlord identity (name, mobile, office) stays on Accommodation Building.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class AccommodationLease(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Accommodation Lease":
            frappe.throw("DocType mismatch")


def validate(doc, method=None):
    if not doc.company:
        from apex_habitat.habitat.doctype.habitat_settings.habitat_settings import get_default_company
        doc.company = get_default_company()

    if doc.lease_end_date and doc.lease_start_date:
        if doc.lease_end_date <= doc.lease_start_date:
            frappe.throw(_("Lease End Date must be after Lease Start Date."))

    due_day = doc.rent_due_day or 1
    if not (1 <= due_day <= 28):
        frappe.throw(_("Rent Due Day must be between 1 and 28."))

    doc.total_scheduled_sar = sum(
        flt(row.amount_sar) for row in (doc.payment_schedule or [])
    )
