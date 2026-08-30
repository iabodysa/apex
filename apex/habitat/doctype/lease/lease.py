# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, flt, getdate

from apex.apex_core.utils.company import resolve_company
from apex.apex_core.utils.date_ranges import has_overlapping_record

_CYCLE_MONTHS = {
    "Monthly": 1,
    "Quarterly": 3,
    "Semi-Annual": 6,
    "Annual": 12,
}


class Lease(Document):
    pass


def _cycle_months(doc):
    return _CYCLE_MONTHS.get(doc.billing_cycle or "Monthly", 1)


def _instalment_amount(doc):
    return flt(doc.rent_amount) * _cycle_months(doc)


def validate(doc, method=None):
    if not doc.company:
        doc.company = resolve_company("Habitat")

    if doc.lease_end_date and doc.lease_start_date:
        if getdate(doc.lease_end_date) <= getdate(doc.lease_start_date):
            frappe.throw(_("Lease End Date must be after Lease Start Date."))

    if doc.first_payment_date and doc.lease_start_date:
        if getdate(doc.first_payment_date) < getdate(doc.lease_start_date):
            frappe.throw(_("First Payment Date cannot be before Lease Start Date."))

    share = flt(doc.company_share_pct)
    if not (0 <= share <= 100):
        frappe.throw(_("Utility Cost Share must be between 0 and 100."))

    if doc.building and doc.lease_start_date and doc.lease_end_date:
        conflict = has_overlapping_record(
            "Lease",
            {"building": doc.building},
            "lease_start_date",
            "lease_end_date",
            doc.lease_start_date,
            doc.lease_end_date,
            doc.name,
        )
        if conflict:
            frappe.throw(
                _("An overlapping lease already exists for this building: {0}").format(conflict)
            )

    _maybe_build_schedule(doc)

    doc.total_scheduled = sum(
        flt(row.amount) for row in (doc.payment_schedule or [])
    )


_SCHEDULE_DRIVER_FIELDS = ("rent_amount", "billing_cycle", "first_payment_date", "lease_end_date")


def _maybe_build_schedule(doc):
    if not doc.payment_schedule:
        _build_schedule(doc)
        return
    if doc.docstatus == 0 and not doc.is_new() and any(
        doc.has_value_changed(f) for f in _SCHEDULE_DRIVER_FIELDS
    ):
        _build_schedule(doc)


def _build_schedule(doc):
    if not (doc.first_payment_date and doc.lease_end_date and flt(doc.rent_amount) > 0):
        return

    step = _cycle_months(doc)
    amount = _instalment_amount(doc)

    doc.payment_schedule = []
    anchor = getdate(doc.first_payment_date)
    end = getdate(doc.lease_end_date)

    n = 0
    due = anchor
    while due <= end:
        doc.append("payment_schedule", {
            "due_date": due,
            "amount": amount,
            "status": "Unpaid",
        })
        n += 1
        due = getdate(add_months(anchor, step * n))


@frappe.whitelist(methods=["POST"])
def regenerate_schedule(name):
    doc = frappe.get_doc("Lease", name)
    frappe.has_permission("Lease", "write", doc=doc, throw=True)

    if doc.docstatus != 0:
        frappe.throw(_("Payment schedule can only be regenerated on a Draft lease."))
    doc.payment_schedule = []
    _build_schedule(doc)
    doc.total_scheduled = sum(flt(r.amount) for r in doc.payment_schedule)
    doc.save()
    return len(doc.payment_schedule)
