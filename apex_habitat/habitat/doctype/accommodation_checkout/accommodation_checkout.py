"""Accommodation Checkout controller.

Vacate transaction with a custody-clearance gate. Damage deduction posting is
gated behind Habitat Settings and disabled by default.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class AccommodationCheckout(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Accommodation Checkout":
            frappe.throw("DocType mismatch")


def validate(doc, method=None):
    for row in doc.custody_return_items or []:
        if row.return_status != "Returned":
            doc.custody_cleared = 0
            frappe.throw(
                _("All custody items must be marked Returned before submission.")
            )
    if doc.custody_return_items:
        doc.custody_cleared = 1


def on_submit(doc, method=None):
    # Close the assignment by recording the check-out date. The assignment is
    # kept as a submitted historical record (not cancelled): the daily cost
    # allocation job stops future rows because it filters on an unset
    # check_out_date, and the stay history is preserved for audit and reports.
    assignment = frappe.get_doc("Accommodation Assignment", doc.assignment)
    assignment.db_set("check_out_date", doc.checkout_date)

    frappe.db.set_value("Accommodation Bed", doc.bed, "status", "Available")

    # Damage recovery is intentionally NOT posted here. Custody Damage
    # Assessment is the single authority for damage deductions, so a checkout
    # can never double-charge an employee already charged via that flow.


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is mandatory."))
