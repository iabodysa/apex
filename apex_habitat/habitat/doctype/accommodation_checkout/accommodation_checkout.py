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
    assignment = frappe.get_doc("Accommodation Assignment", doc.assignment)
    assignment.db_set("check_out_date", doc.checkout_date)
    if assignment.docstatus == 1:
        assignment.cancel()

    frappe.db.set_value("Accommodation Bed", doc.bed, "status", "Available")

    settings = frappe.get_single("Habitat Settings")
    if (
        settings.enable_damage_deduction
        and (doc.damage_deduction_amount or 0) > 0
    ):
        cap = settings.max_damage_deduction_per_checkout_sar or 0
        if cap and doc.damage_deduction_amount > cap:
            frappe.throw(
                _("Damage deduction {0} exceeds the per-checkout cap {1}.").format(
                    doc.damage_deduction_amount, cap
                )
            )
        additional_salary = frappe.get_doc(
            {
                "doctype": "Additional Salary",
                "employee": doc.employee,
                "salary_component": "Accommodation Damage Recovery",
                "amount": doc.damage_deduction_amount,
                "payroll_date": doc.checkout_date,
            }
        )
        additional_salary.insert(ignore_permissions=True)
        doc.db_set("linked_additional_salary", additional_salary.name)


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is mandatory."))
