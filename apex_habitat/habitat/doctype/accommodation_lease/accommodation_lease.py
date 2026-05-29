"""Accommodation Lease controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, flt, getdate

_CYCLE_MONTHS = {
    "Monthly": 1,
    "Quarterly": 3,
    "Semi-Annual": 6,
    "Annual": 12,
}


class AccommodationLease(Document):
    pass


def validate(doc, method=None):
    if not doc.company:
        from apex_habitat.apex_core.doctype.habitat_settings.habitat_settings import get_default_company
        doc.company = get_default_company()

    if doc.lease_end_date and doc.lease_start_date:
        if getdate(doc.lease_end_date) <= getdate(doc.lease_start_date):
            frappe.throw(_("Lease End Date must be after Lease Start Date."))

    if doc.first_payment_date and doc.lease_start_date:
        if getdate(doc.first_payment_date) < getdate(doc.lease_start_date):
            frappe.throw(_("First Payment Date cannot be before Lease Start Date."))

    share = flt(doc.company_share_pct)
    if not (0 <= share <= 100):
        frappe.throw(_("Utility Cost Share must be between 0 and 100."))

    # Reject a second lease whose term overlaps an existing (non-cancelled) lease
    # for the same building.
    if doc.building and doc.lease_start_date and doc.lease_end_date:
        conflict = frappe.db.exists(
            "Accommodation Lease",
            {
                "building": doc.building,
                "docstatus": ["!=", 2],
                "name": ["!=", doc.name or ""],
                "lease_start_date": ["<=", doc.lease_end_date],
                "lease_end_date": [">=", doc.lease_start_date],
            },
        )
        if conflict:
            frappe.throw(
                _("An overlapping lease already exists for this building: {0}").format(conflict)
            )

    if not doc.payment_schedule:
        _build_schedule(doc)

    doc.total_scheduled = sum(
        flt(row.amount) for row in (doc.payment_schedule or [])
    )


def _build_schedule(doc):
    """Populate payment_schedule rows from first_payment_date + billing_cycle."""
    if not (doc.first_payment_date and doc.lease_end_date and flt(doc.rent_amount) > 0):
        return

    step = _CYCLE_MONTHS.get(doc.billing_cycle or "Monthly", 1)
    amount = flt(doc.rent_amount) * step

    doc.payment_schedule = []
    due = getdate(doc.first_payment_date)
    end = getdate(doc.lease_end_date)

    while due <= end:
        doc.append("payment_schedule", {
            "due_date": due,
            "amount": amount,
            "status": "Unpaid",
        })
        due = getdate(add_months(due, step))


@frappe.whitelist(methods=["POST"])
def regenerate_schedule(name):
    """Force-rebuild the payment schedule (clears existing rows)."""
    if not frappe.has_permission("Accommodation Lease", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    doc = frappe.get_doc("Accommodation Lease", name)
    if doc.docstatus != 0:
        frappe.throw(_("Payment schedule can only be regenerated on a Draft lease."))
    doc.payment_schedule = []
    _build_schedule(doc)
    doc.total_scheduled = sum(flt(r.amount) for r in doc.payment_schedule)
    try:
        doc.save()
    except Exception:
        frappe.db.rollback()
        frappe.throw(_("Could not save changes. Please try again or contact support."))
    return len(doc.payment_schedule)
