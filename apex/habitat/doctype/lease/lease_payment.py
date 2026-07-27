# Copyright (c) 2026, AFMCO and contributors
"""Raising the rent for one lease instalment as a payment that settles a real payable.

The Generate Payment button used to build a Payment Entry in the browser and copy the
scheduled rent onto ``paid_amount``. That document carried no ``references`` row, so it
was an ON-ACCOUNT payment: it closed no landlord invoice, moved no
``outstanding_amount``, and reconciled nothing — while reading, on screen, exactly like
the rent being paid. This module routes the same button through
``apex_core.utils.payable_allocation``, the shared engine the Telecom Contract payment
already uses, so the amount and the allocation both come from ERPNext's own payable
logic instead of from the rent schedule.

What is lease-specific and therefore lives here: which lease is eligible, which
instalment a payment covers, and how an already-raised payment is found again.

Finding it again is DERIVED, not stored. The Lease has no field to hold a payment link
and needs none: the payment itself carries the identifying pair — ``reference_no`` names
the lease, ``reference_date`` the instalment — and a schedule holds at most one row per
due date. Reading the answer back off the ledger is also what makes a cancelled payment
show as cancelled, instead of as a stored link to a document whose state nobody re-read.
It is why no cancel exemption is needed here either: with nothing on the lease linking
to the payment, Accounts can cancel it without the lease vetoing the cancellation.

Boundary — this layer submits nothing and posts no GL. The Payment Entry is created in
Draft and left for finance to review and submit.

Which document type gets raised is NOT decided here either. The button used to read the
Payment Routing target in the browser and then pick among three hard-coded branches,
so a deployment could configure one target and be handed another from this one screen.
The target is now read server-side and a mismatch is refused outright: a rent payment
settles a landlord Purchase Invoice, and only a Payment Entry carries the allocation
that does it, so this surface obeys the configuration or declines to act.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from apex.apex_core.payment_router import require_configured_target
from apex.apex_core.utils import payable_allocation

LEASE_DOCTYPE = "Lease"


def _load_eligible_lease(lease: str):
    """Return the submitted Lease the caller may read, or throw.

    The configured payment target is checked FIRST, before anything about this
    particular lease: a deployment routing payments elsewhere cannot raise rent from
    this surface at all, so the lease is beside the point. Gating here rather than in
    the browser puts it on the one path all three endpoints share, where a direct call
    to the API cannot step around it.

    ``lease`` arrives from a whitelisted endpoint, so the existence probe filters on
    ``name``: the positional form answers the value back without querying when it equals
    the DocType (database.py:1259), letting the literal string "Lease" clear this gate
    and reach ``get_doc`` — a bare framework 404 in place of the named refusal below.
    """
    require_configured_target(payable_allocation.PAYMENT_ENTRY_DOCTYPE)
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
    """The rent schedule row this payment covers, or throw.

    The due date is re-resolved against the lease's own schedule rather than trusted
    from the dialog: it is the period key, and a payment dated to an instalment the
    lease does not have would be idempotent against nothing.
    """
    wanted = getdate(due_date) if due_date else None
    if not wanted:
        frappe.throw(_("Select the rent instalment this payment covers."))
    for row in lease_doc.payment_schedule or []:
        if row.due_date and getdate(row.due_date) == wanted:
            return row
    frappe.throw(
        _("Lease {0} has no rent instalment due on {1}.").format(lease_doc.name, wanted)
    )


def _raised_payment(lease_doc, due_date):
    """The Payment Entry already raised for this instalment, or ``None``.

    Cancelled payments are deliberately included: the instalment WAS paid and reversed,
    and reporting that is the point — a probe that skipped them would quietly raise a
    second payment for a period whose first one is sitting cancelled in the ledger.
    """
    return frappe.db.get_value(
        payable_allocation.PAYMENT_ENTRY_DOCTYPE,
        {
            "reference_no": lease_doc.name,
            "reference_date": getdate(due_date),
            "party_type": "Supplier",
            "party": lease_doc.landlord,
        },
        "name",
        order_by="creation asc",
    )


@frappe.whitelist()
def list_rent_payables(lease: str):
    """The submitted Purchase Invoices a rent payment for this lease may settle.

    Read-only. An empty list is the "fail closed / hide the action" signal: with no
    approved landlord invoice there is nothing a rent payment could be allocated to.
    """
    lease_doc = _load_eligible_lease(lease)
    return payable_allocation.list_payables(lease_doc.company, lease_doc.landlord)


@frappe.whitelist()
def get_rent_payment_status(lease: str, due_date: str):
    """What this instalment actually looks like right now — settlement derived from the
    live Payment Entry, so cancelling it in Accounts reverses the status with no
    reversal code and no stored field to drift out of step with the ledger."""
    lease_doc = _load_eligible_lease(lease)
    row = _instalment(lease_doc, due_date)
    status = payable_allocation.settlement_of(_raised_payment(lease_doc, row.due_date))
    status["due_date"] = str(getdate(row.due_date))
    status["scheduled_amount"] = flt(row.amount)
    status["payable_invoices"] = payable_allocation.payable_count(
        lease_doc.company, lease_doc.landlord
    )
    return status


@frappe.whitelist(methods=["POST"])
def create_rent_payment(lease: str, due_date: str, purchase_invoice: str | None = None):
    """Create (or return) a draft Payment Entry ALLOCATED against ``purchase_invoice``
    for one rent instalment. Left in Draft — Apex posts no GL and never submits it."""
    lease_doc = _load_eligible_lease(lease)
    payable_allocation.require_target(payable_allocation.PAYMENT_ENTRY_DOCTYPE)

    # Serialize concurrent calls for the same lease: without the lock two clicks both
    # clear the probe below and one instalment ends up with two payments.
    frappe.db.get_value(LEASE_DOCTYPE, lease_doc.name, "name", for_update=True)
    lease_doc.reload()
    row = _instalment(lease_doc, due_date)

    existing = _raised_payment(lease_doc, row.due_date)
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
    payment.insert(ignore_permissions=True)  # audit-ok — create-permission enforced above
    return _result(payment.name, False)


def _result(document_name, existing):
    return {
        "document_type": payable_allocation.PAYMENT_ENTRY_DOCTYPE,
        "document_name": document_name,
        "existing": existing,
    }
