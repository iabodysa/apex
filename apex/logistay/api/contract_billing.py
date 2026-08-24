# Copyright (c) 2026, afmcoltd
"""Guarded billing actions on a submitted Telecom Contract.

Two POST-only actions turn an in-force contract into draft procurement/finance
paperwork, one set per billing period:

* ``create_purchase_request`` -> a draft native **Material Request** (Purchase),
* ``create_payment_entry``    -> a draft native **Payment Entry** ALLOCATED against
  a submitted **Purchase Invoice**.

Why a Purchase Invoice is required, and how one is chosen and guarded, is
``apex_core.utils.payable_allocation`` — the shared engine a building Lease raises its
rent payment through as well. This module contributes only what is telecom's: which
contract is eligible, that a billing period is one YYYY-MM, and the billing log that
records one document per (contract, period, type).

Boundary — this layer posts NO GL and submits NOTHING. Both targets are created in
Draft and left for finance to review and submit; a Payment Entry posts its ledger
only on its own submit, which never happens here. Settlement is therefore never
stored on the contract: it is DERIVED from the live Payment Entry by
``get_billing_status``, so a cancelled payment reverses the operational status with
no reversal code and no field to drift out of step with the ledger. That reversal is
only reachable because ``allow_cancel_despite_billing_log`` stops the contract's own
billing log from vetoing the cancellation; deleting a cited payment stays blocked.

The two inserts pass ``ignore_permissions`` because the telecom operator who raises the billing
is not a finance user and must not become one: the Material Request and Payment Entry create
permission belongs to Purchase and Accounts roles, and granting those to a coordinator would hand
them the whole procurement and payment surface. Both land in Draft for finance to review. The
billing-log append onto the contract carries no such flag — every role reaching this endpoint
already holds ``write`` on Telecom Contract within its own company scope.

Every action:
  * requires an eligible submitted contract the caller may read (company-scoped),
  * requires the caller's create permission on the target DocType,
  * fails closed when the target DocType or a prerequisite (service item, company
    accounts, an eligible payable invoice) is missing,
  * is duplicate-safe: a second call for the same (contract, period, type) returns
    the existing draft rather than creating another, serialized by a row lock.

The lock and the duplicate check must be the SAME read: ``get_doc(..., for_update=True)``
locks the contract row and reads its ``billing_documents`` children under that lock. A
discarded lock followed by a plain ``reload()`` still answers from the opening snapshot
under REPEATABLE READ, so the loser raises a second draft and deletes the winner's row.
"""

from __future__ import annotations

import calendar
import datetime

import frappe
from frappe import _
from frappe.utils import getdate, today

from apex.apex_core.utils import payable_allocation


CONTRACT_DOCTYPE = "Telecom Contract"
PURCHASE_REQUEST_DOCTYPE = "Material Request"
PAYMENT_ENTRY_DOCTYPE = payable_allocation.PAYMENT_ENTRY_DOCTYPE


def _load_eligible_contract(contract: str):
    """Return the submitted Telecom Contract the caller may read, or throw.

    """
    if not contract or not frappe.db.exists("Telecom Contract", {"name": contract}):
        frappe.throw(_("Telecom Contract {0} does not exist.").format(contract))
    doc = frappe.get_doc("Telecom Contract", contract)
    doc.check_permission("read")
    if doc.docstatus != 1:
        frappe.throw(_("Billing documents can only be raised from a submitted contract."))
    return doc


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
    """Return an already-recorded draft for this (period, type) if it still exists.

    """
    for row in contract_doc.billing_documents or []:
        if row.billing_period == billing_period and row.document_type == document_type:
            if row.document_name and frappe.db.exists(document_type, {"name": row.document_name}):
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
    contract_doc.flags.ignore_validate_update_after_submit = True
    contract_doc.save()


def _result(document_type, document_name, existing):
    """Builds the standard document_type, document_name, and existing response for a billing action."""
    return {"document_type": document_type, "document_name": document_name, "existing": existing}


@frappe.whitelist(methods=["POST"])
def create_purchase_request(contract: str, billing_period: str):
    """Create (or return) a draft Material Request (Purchase) for one billing period."""
    contract_doc = _load_eligible_contract(contract)
    payable_allocation.validate_target(PURCHASE_REQUEST_DOCTYPE)
    billing_period = _normalize_period(billing_period)

    if not contract_doc.service_item:
        frappe.throw(
            _("Set a Service Item on the contract before raising a purchase request.")
        )

    contract_doc = frappe.get_doc(CONTRACT_DOCTYPE, contract_doc.name, for_update=True)

    existing = _existing_link(contract_doc, billing_period, PURCHASE_REQUEST_DOCTYPE)
    if existing:
        return _result(PURCHASE_REQUEST_DOCTYPE, existing, True)

    period_end = _period_end(billing_period)
    raised_on = today()
    needed_by = max(period_end, getdate(raised_on))
    uom = frappe.db.get_value("Item", contract_doc.service_item, "stock_uom") or "Nos"
    description = _("Telecom service — {0} — {1} ({2})").format(
        contract_doc.supplier, billing_period, contract_doc.name
    )
    mr = frappe.new_doc(PURCHASE_REQUEST_DOCTYPE)
    mr.material_request_type = "Purchase"
    mr.company = contract_doc.company
    mr.transaction_date = raised_on
    mr.schedule_date = needed_by
    mr.append(
        "items",
        {
            "item_code": contract_doc.service_item,
            "qty": 1,
            "uom": uom,
            "schedule_date": needed_by,
            "description": description,
            "cost_center": contract_doc.cost_center,
            "project": contract_doc.project,
        },
    )
    mr.set_missing_values()
    mr.insert(ignore_permissions=True)

    _record_link(
        contract_doc,
        billing_period,
        PURCHASE_REQUEST_DOCTYPE,
        mr.name,
        contract_doc.recurring_amount,
        contract_doc.currency,
    )
    return _result(PURCHASE_REQUEST_DOCTYPE, mr.name, False)


@frappe.whitelist()
def list_payable_invoices(contract: str):
    """The submitted Purchase Invoices a payment for this contract may settle."""
    contract_doc = _load_eligible_contract(contract)
    return payable_allocation.list_payables(contract_doc.company, contract_doc.supplier)


@frappe.whitelist(methods=["POST"])
def create_payment_entry(contract: str, billing_period: str, purchase_invoice: str | None = None):
    """Create (or return) a draft Payment Entry ALLOCATED against ``purchase_invoice``.

    Built by the shared ``payable_allocation`` engine, so the ``references`` row and
    its allocated amount come from ERPNext's own payable logic rather than from an
    amount copied off the contract. Left in Draft — Apex posts no GL and never
    submits it.
    """
    contract_doc = _load_eligible_contract(contract)
    payable_allocation.validate_target(PAYMENT_ENTRY_DOCTYPE)
    billing_period = _normalize_period(billing_period)

    contract_doc = frappe.get_doc(CONTRACT_DOCTYPE, contract_doc.name, for_update=True)

    existing = _existing_link(contract_doc, billing_period, PAYMENT_ENTRY_DOCTYPE)
    if existing:
        return _result(PAYMENT_ENTRY_DOCTYPE, existing, True)

    pe, invoice = payable_allocation.build_allocated_payment(
        contract_doc.company, contract_doc.supplier, purchase_invoice
    )
    pe.posting_date = today()
    pe.cost_center = contract_doc.cost_center or pe.cost_center
    pe.project = contract_doc.project or pe.project
    pe.reference_no = contract_doc.name
    pe.reference_date = _period_end(billing_period)
    pe.remarks = _("Telecom {0} — billing period {1} ({2}), settling {3}.").format(
        contract_doc.supplier, billing_period, contract_doc.name, invoice.name
    )
    pe.insert(ignore_permissions=True)

    _record_link(
        contract_doc,
        billing_period,
        PAYMENT_ENTRY_DOCTYPE,
        pe.name,
        payable_allocation.allocated_total(pe),
        pe.paid_to_account_currency or contract_doc.currency,
    )
    return _result(PAYMENT_ENTRY_DOCTYPE, pe.name, False)


@frappe.whitelist()
def get_billing_status(contract: str, billing_period: str):
    """What this contract's billing period actually looks like right now.

    ``settlement`` is derived by the shared engine, never stored — so a payment
    cancelled in Accounts reverses the operational status here with no reversal code.
    """
    contract_doc = _load_eligible_contract(contract)
    billing_period = _normalize_period(billing_period)

    payment_name = _existing_link(contract_doc, billing_period, PAYMENT_ENTRY_DOCTYPE)
    status = payable_allocation.settlement_of(payment_name)
    status["billing_period"] = billing_period
    status["payable_invoices"] = payable_allocation.payable_count(
        contract_doc.company, contract_doc.supplier
    )
    return status


def allow_cancel_despite_billing_log(doc, method=None):
    """Stop the contract's billing log from vetoing a Payment Entry cancellation.

    """
    existing = tuple(doc.get("ignore_linked_doctypes") or ())
    if CONTRACT_DOCTYPE not in existing:
        doc.ignore_linked_doctypes = (*existing, CONTRACT_DOCTYPE)
