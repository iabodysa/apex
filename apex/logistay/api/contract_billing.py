# Copyright (c) 2026, AFMCO and contributors
"""Guarded billing actions on a submitted Telecom Contract.

Two POST-only actions turn an in-force contract into draft procurement/finance
paperwork, one set per billing period:

* ``create_purchase_request`` -> a draft native **Material Request** (Purchase),
* ``create_payment_entry``    -> a draft native **Payment Entry** ALLOCATED against
  a submitted **Purchase Invoice**.

Why a Purchase Invoice is required. A Payment Entry with no ``references`` row is
an ON-ACCOUNT payment in ERPNext: it debits the supplier's payable in aggregate and
settles no particular bill, so no invoice's ``outstanding_amount`` moves and nothing
reconciles. Presenting that as "the telecom bill is paid" is a claim the ledger does
not support. The native primitive for settling a payable is
``erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry``, which
builds the Payment Entry FROM the invoice and fills the ``references`` child table
with the allocation (payment_entry.py:3008). That function is the whole mechanism
here — this module only chooses and guards the source invoice.

Boundary — this layer posts NO GL and submits NOTHING. Both targets are created in
Draft and left for finance to review and submit; a Payment Entry posts its ledger
only on its own submit, which never happens here. Settlement is therefore never
stored on the contract: it is DERIVED from the live Payment Entry by
``get_billing_status``, so a cancelled payment reverses the operational status with
no reversal code and no field to drift out of step with the ledger.

Every action:
  * requires an eligible submitted contract the caller may read (company-scoped),
  * requires the caller's create permission on the target DocType,
  * fails closed when the target DocType or a prerequisite (service item, company
    accounts, an eligible payable invoice) is missing,
  * is duplicate-safe: a second call for the same (contract, period, type) returns
    the existing draft rather than creating another, serialized by a row lock.
"""

from __future__ import annotations

import calendar
import datetime

import frappe
from frappe import _
from frappe.utils import flt, today

PURCHASE_REQUEST_DOCTYPE = "Material Request"
PAYMENT_ENTRY_DOCTYPE = "Payment Entry"
# The approved native payable a telecom payment must settle. A Payment Entry is
# raised FROM one of these, never on account.
PAYABLE_SOURCE_DOCTYPE = "Purchase Invoice"


# Shared guards


def _load_eligible_contract(contract: str):
    """Return the submitted Telecom Contract the caller may read, or throw."""
    if not contract or not frappe.db.exists("Telecom Contract", contract):
        frappe.throw(_("Telecom Contract {0} does not exist.").format(contract))
    doc = frappe.get_doc("Telecom Contract", contract)
    # Company-scoped read permission (has_permission hook enforces company scope).
    doc.check_permission("read")
    if doc.docstatus != 1:
        frappe.throw(_("Billing documents can only be raised from a submitted contract."))
    return doc


def _require_target(doctype: str) -> None:
    """Fail closed when the target DocType is not installed, or the caller lacks
    create permission on it."""
    if not frappe.db.exists("DocType", doctype):
        frappe.throw(_("The {0} DocType is not available on this site.").format(_(doctype)))
    frappe.has_permission(doctype, "create", throw=True)


def _normalize_period(billing_period: str) -> str:
    """Validate a YYYY-MM billing period and return it normalized."""
    period = (billing_period or "").strip()
    try:
        parsed = datetime.datetime.strptime(period, "%Y-%m")
    except ValueError:
        frappe.throw(_("Billing Period must look like 2026-07 (year and month)."))
    return parsed.strftime("%Y-%m")


def _period_end(billing_period: str):
    """Last calendar day of a YYYY-MM period."""
    parsed = datetime.datetime.strptime(billing_period, "%Y-%m")
    last_day = calendar.monthrange(parsed.year, parsed.month)[1]
    return datetime.date(parsed.year, parsed.month, last_day)


def _existing_link(contract_doc, billing_period: str, document_type: str):
    """Return an already-recorded draft for this (period, type) if it still exists."""
    for row in contract_doc.billing_documents or []:
        if row.billing_period == billing_period and row.document_type == document_type:
            if row.document_name and frappe.db.exists(document_type, row.document_name):
                return row.document_name
    return None


def _record_link(contract_doc, billing_period, document_type, document_name, amount, currency):
    """Log the created draft onto the (submitted) contract's billing table."""
    contract_doc.append(
        "billing_documents",
        {
            "billing_period": billing_period,
            "document_type": document_type,
            "document_name": document_name,
            "amount": amount,
            "currency": currency,
            "created_on": frappe.utils.now_datetime(),
        },
    )
    # billing_documents is allow_on_submit; only this log row changes on the
    # submitted contract, so skip the after-submit field-change validation.
    contract_doc.flags.ignore_validate_update_after_submit = True
    contract_doc.save(ignore_permissions=True)  # audit-ok — append-only billing log


def _result(document_type, document_name, existing):
    return {"document_type": document_type, "document_name": document_name, "existing": existing}


# Purchase request (Material Request)


@frappe.whitelist(methods=["POST"])
def create_purchase_request(contract: str, billing_period: str):
    """Create (or return) a draft Material Request (Purchase) for one billing period."""
    contract_doc = _load_eligible_contract(contract)
    _require_target(PURCHASE_REQUEST_DOCTYPE)
    billing_period = _normalize_period(billing_period)

    if not contract_doc.service_item:
        frappe.throw(
            _("Set a Service Item on the contract before raising a purchase request.")
        )

    # Serialize concurrent calls for the same contract so duplicates cannot race.
    frappe.db.get_value("Telecom Contract", contract_doc.name, "name", for_update=True)
    contract_doc.reload()

    existing = _existing_link(contract_doc, billing_period, PURCHASE_REQUEST_DOCTYPE)
    if existing:
        return _result(PURCHASE_REQUEST_DOCTYPE, existing, True)

    period_end = _period_end(billing_period)
    uom = frappe.db.get_value("Item", contract_doc.service_item, "stock_uom") or "Nos"
    description = _("Telecom service — {0} — {1} ({2})").format(
        contract_doc.supplier, billing_period, contract_doc.name
    )
    mr = frappe.new_doc(PURCHASE_REQUEST_DOCTYPE)
    mr.material_request_type = "Purchase"
    mr.company = contract_doc.company
    mr.transaction_date = today()
    mr.schedule_date = period_end
    mr.append(
        "items",
        {
            "item_code": contract_doc.service_item,
            "qty": 1,
            "uom": uom,
            "schedule_date": period_end,
            "description": description,
            "cost_center": contract_doc.cost_center,
            "project": contract_doc.project,
        },
    )
    mr.set_missing_values()
    mr.insert(ignore_permissions=True)  # audit-ok — create-permission enforced above

    _record_link(
        contract_doc,
        billing_period,
        PURCHASE_REQUEST_DOCTYPE,
        mr.name,
        contract_doc.recurring_amount,
        contract_doc.currency,
    )
    return _result(PURCHASE_REQUEST_DOCTYPE, mr.name, False)


# Payment (native Payment Entry allocated against a Purchase Invoice)


def _require_money_source(company: str) -> None:
    """Fail closed unless the company has a default Cash or Bank account.

    ``get_payment_entry`` resolves this itself via ``get_bank_cash_account``
    (payment_entry.py:3226) but does NOT guard the miss: with neither account it
    dereferences ``bank.account`` on a None and raises AttributeError
    (payment_entry.py:2940). Checking first turns that crash into a message naming
    what finance must configure.
    """
    from erpnext.accounts.doctype.payment_entry.payment_entry import (
        get_default_bank_cash_account,
    )

    source = get_default_bank_cash_account(company, "Cash") or get_default_bank_cash_account(
        company, "Bank"
    )
    if not source or not source.get("account"):
        frappe.throw(
            _(
                "Configure a default Cash or Bank account on company {0} before raising a payment."
            ).format(company)
        )


def _payable_invoice_filters(contract_doc) -> dict:
    """Filters selecting the submitted, still-outstanding Purchase Invoices this
    contract's payment may settle: the contract's own supplier and company only."""
    return {
        "docstatus": 1,
        "company": contract_doc.company,
        "supplier": contract_doc.supplier,
        "outstanding_amount": [">", 0],
    }


def _payable_invoice_count(contract_doc):
    """How many eligible payables exist, or ``None`` when the caller may not read
    invoices at all — so a status read never throws for a SIM Operations User who
    can see the contract but not the finance documents behind it."""
    if not frappe.db.exists("DocType", PAYABLE_SOURCE_DOCTYPE):
        return 0
    if not frappe.has_permission(PAYABLE_SOURCE_DOCTYPE, "read"):
        return None
    return frappe.db.count(PAYABLE_SOURCE_DOCTYPE, _payable_invoice_filters(contract_doc))


@frappe.whitelist()
def list_payable_invoices(contract: str):
    """The submitted Purchase Invoices a payment for this contract may settle.

    Read-only. An empty list is the "fail closed / hide the action" signal: with no
    approved payable there is nothing a payment could legitimately be allocated to.
    """
    contract_doc = _load_eligible_contract(contract)
    if not frappe.db.exists("DocType", PAYABLE_SOURCE_DOCTYPE):
        return []
    frappe.has_permission(PAYABLE_SOURCE_DOCTYPE, "read", throw=True)
    return frappe.get_all(
        PAYABLE_SOURCE_DOCTYPE,
        filters=_payable_invoice_filters(contract_doc),
        fields=["name", "bill_no", "posting_date", "grand_total", "outstanding_amount", "currency"],
        order_by="posting_date asc",
        limit_page_length=50,
    )


def _load_eligible_payable(contract_doc, purchase_invoice: str):
    """Return the submitted Purchase Invoice this payment may settle, or throw.

    Every condition is re-checked here rather than trusted from the picker: the
    caller is a browser and the eligible set can change between listing and paying.
    """
    if not purchase_invoice:
        frappe.throw(
            _(
                "Select the {0} this payment settles. A payment with no invoice behind it "
                "settles nothing in the ledger."
            ).format(_(PAYABLE_SOURCE_DOCTYPE)),
            title=_("Payable Source Required"),
        )
    if not frappe.db.exists(PAYABLE_SOURCE_DOCTYPE, purchase_invoice):
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
    if invoice.company != contract_doc.company:
        frappe.throw(
            _("{0} {1} belongs to company {2}, not the contract's company {3}.").format(
                _(PAYABLE_SOURCE_DOCTYPE), invoice.name, invoice.company, contract_doc.company
            )
        )
    if invoice.supplier != contract_doc.supplier:
        frappe.throw(
            _("{0} {1} is billed by {2}, not the contract's supplier {3}.").format(
                _(PAYABLE_SOURCE_DOCTYPE), invoice.name, invoice.supplier, contract_doc.supplier
            )
        )
    if flt(invoice.outstanding_amount) <= 0:
        frappe.throw(
            _("{0} {1} has nothing outstanding — it is already settled.").format(
                _(PAYABLE_SOURCE_DOCTYPE), invoice.name
            )
        )
    return invoice


def _allocated_total(pe) -> float:
    return sum(flt(row.allocated_amount) for row in (pe.references or []))


@frappe.whitelist(methods=["POST"])
def create_payment_entry(contract: str, billing_period: str, purchase_invoice: str | None = None):
    """Create (or return) a draft Payment Entry ALLOCATED against ``purchase_invoice``.

    Built by the native ``get_payment_entry``, so the ``references`` row and its
    allocated amount come from ERPNext's own payable logic rather than from an
    amount copied off the contract. Left in Draft — Apex posts no GL and never
    submits it.
    """
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    contract_doc = _load_eligible_contract(contract)
    _require_target(PAYMENT_ENTRY_DOCTYPE)
    billing_period = _normalize_period(billing_period)

    frappe.db.get_value("Telecom Contract", contract_doc.name, "name", for_update=True)
    contract_doc.reload()

    existing = _existing_link(contract_doc, billing_period, PAYMENT_ENTRY_DOCTYPE)
    if existing:
        return _result(PAYMENT_ENTRY_DOCTYPE, existing, True)

    invoice = _load_eligible_payable(contract_doc, purchase_invoice)
    _require_money_source(contract_doc.company)

    pe = get_payment_entry(PAYABLE_SOURCE_DOCTYPE, invoice.name)
    # Fail closed rather than persist an on-account payment: if the native builder
    # produced no allocation (the invoice was settled between the check and here),
    # the document would settle nothing while looking like a telecom payment.
    if _allocated_total(pe) <= 0:
        frappe.throw(
            _("No amount could be allocated against {0} {1}. Refresh and try again.").format(
                _(PAYABLE_SOURCE_DOCTYPE), invoice.name
            )
        )

    pe.posting_date = today()
    pe.cost_center = contract_doc.cost_center or pe.cost_center
    pe.project = contract_doc.project or pe.project
    pe.reference_no = contract_doc.name
    pe.reference_date = _period_end(billing_period)
    pe.remarks = _("Telecom {0} — billing period {1} ({2}), settling {3}.").format(
        contract_doc.supplier, billing_period, contract_doc.name, invoice.name
    )
    pe.insert(ignore_permissions=True)  # audit-ok — create-permission enforced above

    _record_link(
        contract_doc,
        billing_period,
        PAYMENT_ENTRY_DOCTYPE,
        pe.name,
        _allocated_total(pe),
        pe.paid_to_account_currency or contract_doc.currency,
    )
    return _result(PAYMENT_ENTRY_DOCTYPE, pe.name, False)


# Derived settlement status


# Settlement states, in the order the operator sees them. Stored nowhere: each one
# is read from the live Payment Entry, so cancelling the payment reverses the status
# with no reversal code and nothing to drift out of step with the ledger.
NOT_RAISED = "Not Raised"
AWAITING_APPROVAL = "Awaiting Finance Approval"
SETTLED = "Settled"
REVERSED = "Payment Cancelled"


@frappe.whitelist()
def get_billing_status(contract: str, billing_period: str):
    """What this contract's billing period actually looks like right now.

    ``settlement`` is derived, never stored:
      * no linked Payment Entry              -> Not Raised
      * linked but still Draft               -> Awaiting Finance Approval
      * submitted WITH an allocated reference -> Settled
      * cancelled                             -> Payment Cancelled

    A submitted Payment Entry carrying no allocation is deliberately NOT reported as
    settled: it moved money on account and closed no invoice, so calling it a
    settlement would be the exact claim this module exists to stop.
    """
    contract_doc = _load_eligible_contract(contract)
    billing_period = _normalize_period(billing_period)

    payment_name = _existing_link(contract_doc, billing_period, PAYMENT_ENTRY_DOCTYPE)
    status = {
        "billing_period": billing_period,
        "payment_entry": payment_name,
        "settlement": NOT_RAISED,
        "allocated_amount": 0.0,
        "payable_invoices": _payable_invoice_count(contract_doc),
    }
    if not payment_name:
        return status

    payment = frappe.get_doc(PAYMENT_ENTRY_DOCTYPE, payment_name)
    allocated = _allocated_total(payment)
    status["allocated_amount"] = allocated
    if payment.docstatus == 2:
        status["settlement"] = REVERSED
    elif payment.docstatus == 1 and allocated > 0:
        status["settlement"] = SETTLED
    else:
        status["settlement"] = AWAITING_APPROVAL
    return status
