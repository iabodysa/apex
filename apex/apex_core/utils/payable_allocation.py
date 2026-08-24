# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import (
    get_default_bank_cash_account,
    get_payment_entry,
)
from frappe import _
from frappe.utils import flt

PAYABLE_SOURCE_DOCTYPE = "Purchase Invoice"
PAYMENT_ENTRY_DOCTYPE = "Payment Entry"

NOT_RAISED = "Not Raised"
AWAITING_APPROVAL = "Awaiting Finance Approval"
SETTLED = "Settled"
REVERSED = "Payment Cancelled"


def validate_target(doctype: str) -> None:
    if not frappe.db.exists("DocType", doctype):
        frappe.throw(_("The {0} DocType is not available on this site.").format(_(doctype)))
    frappe.has_permission(doctype, "create", throw=True)


def payable_filters(company: str, supplier: str) -> dict:
    return {
        "docstatus": 1,
        "company": company,
        "supplier": supplier,
        "outstanding_amount": [">", 0],
    }


def list_payables(company: str, supplier: str, limit: int = 50) -> list:
    if not frappe.db.exists("DocType", PAYABLE_SOURCE_DOCTYPE):
        return []
    frappe.has_permission(PAYABLE_SOURCE_DOCTYPE, "read", throw=True)
    return frappe.get_list(
        PAYABLE_SOURCE_DOCTYPE,
        filters=payable_filters(company, supplier),
        fields=["name", "bill_no", "posting_date", "grand_total", "outstanding_amount", "currency"],
        order_by="posting_date asc",
        limit_page_length=limit,
    )


def payable_count(company: str, supplier: str):
    if not frappe.db.exists("DocType", PAYABLE_SOURCE_DOCTYPE):
        return 0
    if not frappe.has_permission(PAYABLE_SOURCE_DOCTYPE, "read"):
        return None
    rows = frappe.get_list(
        PAYABLE_SOURCE_DOCTYPE,
        filters=payable_filters(company, supplier),
        fields=["count(name) as count"],
        limit_page_length=1,
    )
    return int(rows[0].get("count") or 0) if rows else 0


def load_eligible_payable(company: str, supplier: str, purchase_invoice: str | None):
    if not purchase_invoice:
        frappe.throw(
            _(
                "Select the {0} this payment settles. A payment with no invoice behind it "
                "settles nothing in the ledger."
            ).format(_(PAYABLE_SOURCE_DOCTYPE)),
            title=_("Payable Source Required"),
        )
    if not frappe.db.exists(PAYABLE_SOURCE_DOCTYPE, {"name": purchase_invoice}):
        frappe.throw(
            _("{0} {1} does not exist.").format(_(PAYABLE_SOURCE_DOCTYPE), purchase_invoice)
        )
    invoice = frappe.get_doc(PAYABLE_SOURCE_DOCTYPE, purchase_invoice)
    invoice.check_permission("read")

    if invoice.docstatus != 1:
        frappe.throw(
            _("{0} {1} is not submitted. Only an approved invoice can be paid.").format(
                _(PAYABLE_SOURCE_DOCTYPE), invoice.name
            )
        )
    if invoice.company != company:
        frappe.throw(
            _("{0} {1} belongs to company {2}, not company {3}.").format(
                _(PAYABLE_SOURCE_DOCTYPE), invoice.name, invoice.company, company
            )
        )
    if invoice.supplier != supplier:
        frappe.throw(
            _("{0} {1} is billed by {2}, not by {3}.").format(
                _(PAYABLE_SOURCE_DOCTYPE), invoice.name, invoice.supplier, supplier
            )
        )
    if flt(invoice.outstanding_amount) <= 0:
        frappe.throw(
            _("{0} {1} has nothing outstanding — it is already settled.").format(
                _(PAYABLE_SOURCE_DOCTYPE), invoice.name
            )
        )
    return invoice


def validate_money_source(company: str) -> None:
    source = get_default_bank_cash_account(company, "Cash") or get_default_bank_cash_account(
        company, "Bank"
    )
    if not source or not source.get("account"):
        frappe.throw(
            _(
                "Configure a default Cash or Bank account on company {0} before raising a payment."
            ).format(company)
        )


def allocated_total(payment) -> float:
    return sum(flt(row.allocated_amount) for row in (payment.references or []))


def build_allocated_payment(company: str, supplier: str, purchase_invoice: str | None):
    invoice = load_eligible_payable(company, supplier, purchase_invoice)
    validate_money_source(company)

    payment = get_payment_entry(PAYABLE_SOURCE_DOCTYPE, invoice.name)
    if allocated_total(payment) <= 0:
        frappe.throw(
            _("No amount could be allocated against {0} {1}. Refresh and try again.").format(
                _(PAYABLE_SOURCE_DOCTYPE), invoice.name
            )
        )
    return payment, invoice


def settlement_of(payment_name: str | None) -> dict:
    if not payment_name:
        return {"payment_entry": None, "settlement": NOT_RAISED, "allocated_amount": 0.0}

    payment = frappe.get_doc(PAYMENT_ENTRY_DOCTYPE, payment_name)
    allocated = allocated_total(payment)
    if payment.docstatus == 2:
        settlement = REVERSED
    elif payment.docstatus == 1 and allocated > 0:
        settlement = SETTLED
    else:
        settlement = AWAITING_APPROVAL
    return {
        "payment_entry": payment_name,
        "settlement": settlement,
        "allocated_amount": allocated,
    }
