"""Accommodation Checkout controller.

Vacate transaction with a custody-clearance gate. Damage deduction posting is
gated behind Habitat Settings and disabled by default.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from apex_habitat.habitat.doctype.accommodation_assignment.accommodation_assignment import recalculate_spatial


class AccommodationCheckout(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Accommodation Checkout":
            frappe.throw("DocType mismatch")


def validate(doc, method=None):
    if not doc.assignment:
        frappe.throw(_("Accommodation Assignment is required."))

    assignment = frappe.get_doc("Accommodation Assignment", doc.assignment)

    if assignment.docstatus != 1:
        frappe.throw(_("Linked Accommodation Assignment must be submitted."))

    if assignment.check_out_date:
        frappe.throw(_("Linked Accommodation Assignment already has a check-out date: {0}").format(assignment.check_out_date))

    if doc.checkout_date and assignment.check_in_date and getdate(doc.checkout_date) < getdate(assignment.check_in_date):
        frappe.throw(_("Checkout date cannot be earlier than assignment check-in date."))

    duplicate = frappe.db.get_value(
        "Accommodation Checkout",
        {"assignment": doc.assignment, "docstatus": 1, "name": ["!=", doc.name]},
    )
    if duplicate:
        frappe.throw(_("A submitted Accommodation Checkout already exists for this assignment: {0}").format(duplicate))

    if not doc.employee:
        doc.employee = assignment.employee
    if not doc.bed:
        doc.bed = assignment.bed
    if not doc.cost_center:
        doc.cost_center = assignment.cost_center

    _VALID_TERMINAL = {"Returned", "Lost", "Damaged"}
    for row in doc.custody_return_items or []:
        if row.return_status not in _VALID_TERMINAL:
            doc.custody_cleared = 0
            frappe.throw(
                _("Each custody item must be marked Returned, Lost, or Damaged before submission.")
            )
    if doc.custody_return_items:
        all_returned = all(r.return_status == "Returned" for r in doc.custody_return_items)
        doc.custody_cleared = 1 if all_returned else 0


def on_submit(doc, method=None):
    # Close the assignment by recording the check-out date. The assignment is
    # kept as a submitted historical record (not cancelled): the daily cost
    # allocation job stops future rows because it filters on an unset
    # check_out_date, and the stay history is preserved for audit and reports.
    assignment = frappe.get_doc("Accommodation Assignment", doc.assignment)
    assignment.db_set("check_out_date", doc.checkout_date)
    assignment.add_comment("Comment", _("Check-out processed via {0} on {1}").format(doc.name, doc.checkout_date))

    frappe.db.set_value("Accommodation Bed", doc.bed, "status", "Available")
    recalculate_spatial(assignment.room, assignment.building)

    # Damage recovery is intentionally NOT posted here. Custody Damage
    # Assessment is the single authority for damage deductions, so a checkout
    # can never double-charge an employee already charged via that flow.


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is mandatory."))


def on_cancel(doc, method=None):
    assignment = frappe.get_doc("Accommodation Assignment", doc.assignment)

    later_checkout = frappe.db.get_value(
        "Accommodation Checkout",
        {"assignment": doc.assignment, "docstatus": 1, "name": ["!=", doc.name]},
    )
    if not later_checkout:
        assignment.db_set("check_out_date", None)
        assignment.add_comment("Comment", _("Check-out cancelled. Reason: {0}").format(doc.cancellation_reason))

        active_on_bed = frappe.db.count(
            "Accommodation Assignment",
            {
                "bed": doc.bed,
                "docstatus": 1,
                "check_out_date": ["is", "not set"],
                "name": ["!=", assignment.name],
            },
        )
        if active_on_bed == 0:
            frappe.db.set_value("Accommodation Bed", doc.bed, "status", "Occupied")

        recalculate_spatial(assignment.room, assignment.building)
