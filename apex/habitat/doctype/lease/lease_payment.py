# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from apex.apex_core.payment_router import validate_configured_target
from apex.apex_core.utils import payable_allocation


LEASE_DOCTYPE = "Lease"


def _load_eligible_lease(lease: str):
    validate_configured_target(payable_allocation.PAYMENT_ENTRY_DOCTYPE)
    if not lease or not frappe.db.exists(LEASE_DOCTYPE, {"name": lease}):
        frappe.throw(_("Lease {0} does not exist.").format(lease))
    doc = frappe.get_doc(LEASE_DOCTYPE, lease)
    doc.check_permission("read")
    if doc.docstatus != 1:
        frappe.throw(_("Rent payments can only be raised from a submitted lease."))
    if not doc.landlord:
        frappe.throw(
            _("Set a Landlord on lease {0} before raising a rent payment — a payment needs a party to settle with.").format(doc.name)
        )
    return doc


def _instalment(lease_doc, due_date):
    wanted = getdate(due_date) if due_date else None
    if not wanted:
        frappe.throw(_("Select the rent instalment this payment covers."))
    for row in lease_doc.payment_schedule or []:
        if row.due_date and getdate(row.due_date) == wanted:
            return row
    frappe.throw(
        _("Lease {0} has no rent instalment due on {1}.").format(lease_doc.name, wanted)
    )


@frappe.whitelist()
def list_rent_payables(lease: str):
    lease_doc = _load_eligible_lease(lease)
    return payable_allocation.list_payables(lease_doc.company, lease_doc.landlord)


@frappe.whitelist()
def get_rent_payment_status(lease: str, due_date: str):
    lease_doc = _load_eligible_lease(lease)
    row = _instalment(lease_doc, due_date)
    status = payable_allocation.settlement_of(frappe.db.get_value(
        payable_allocation.PAYMENT_ENTRY_DOCTYPE,
        {
            "reference_no": lease_doc.name,
            "reference_date": getdate(row.due_date),
            "party_type": "Supplier",
            "party": lease_doc.landlord,
        },
        "name",
        order_by="creation asc",
        for_update=False,
    ))
    status["due_date"] = str(getdate(row.due_date))
    status["scheduled_amount"] = flt(row.amount)
    status["payable_invoices"] = payable_allocation.payable_count(
        lease_doc.company, lease_doc.landlord
    )
    return status


@frappe.whitelist(methods=["POST"])
def create_rent_payment(lease: str, due_date: str, purchase_invoice: str | None = None):
    lease_doc = _load_eligible_lease(lease)
    payable_allocation.validate_target(payable_allocation.PAYMENT_ENTRY_DOCTYPE)

    frappe.db.get_value(LEASE_DOCTYPE, lease_doc.name, "name", for_update=True)
    lease_doc.reload()
    row = _instalment(lease_doc, due_date)

    existing = frappe.db.get_value(
        payable_allocation.PAYMENT_ENTRY_DOCTYPE,
        {
            "reference_no": lease_doc.name,
            "reference_date": getdate(row.due_date),
            "party_type": "Supplier",
            "party": lease_doc.landlord,
        },
        "name",
        order_by="creation asc",
        for_update=True,
    )
    if existing:
        return _result(existing, True)

    payment, invoice = payable_allocation.build_allocated_payment(
        lease_doc.company, lease_doc.landlord, purchase_invoice
    )
    payment.posting_date = today()
    payment.reference_no = lease_doc.name
    payment.reference_date = getdate(row.due_date)
    payment.remarks = _("Rent for {0} — instalment due {1} ({2}), settling {3}.").format(
        lease_doc.building, getdate(row.due_date), lease_doc.name, invoice.name
    )
    payment.insert()
    return _result(payment.name, False)


def _result(document_name, existing):
    return {
        "document_type": payable_allocation.PAYMENT_ENTRY_DOCTYPE,
        "document_name": document_name,
        "existing": existing,
    }
