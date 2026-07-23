# Copyright (c) 2026, AFMCO and contributors
"""Guarded billing actions on a submitted Telecom Contract.

Two POST-only actions turn an in-force contract into draft procurement/finance
paperwork, one set per billing period:

* ``create_purchase_request`` -> a draft native **Material Request** (Purchase),
* ``create_payment_order``    -> a draft native **Payment Entry** (Pay/Supplier).

Boundary — this layer posts NO GL and submits NOTHING. Both targets are created
in Draft and left for finance to review and submit; a Payment Entry posts its
ledger only on its own submit, which never happens here. Every action:
  * requires an eligible submitted contract the caller may read (company-scoped),
  * requires the caller's create permission on the target DocType,
  * fails closed when the target DocType or a prerequisite (service item, company
    accounts) is missing,
  * is duplicate-safe: a second call for the same (contract, period, type) returns
    the existing draft rather than creating another, serialized by a row lock.
"""

from __future__ import annotations

import calendar
import datetime

import frappe
from frappe import _
from frappe.utils import today

PURCHASE_REQUEST_DOCTYPE = "Material Request"
PAYMENT_ORDER_DOCTYPE = "Payment Entry"


# --- shared guards ------------------------------------------------------------


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


# --- purchase request (Material Request) --------------------------------------


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


# --- payment order (Payment Entry) --------------------------------------------


def _company_paid_from(company: str):
    """Resolve the company's money-source account (default cash, else bank) for a
    Payment Entry, or ``(None, message)`` naming what finance must configure."""
    from erpnext.accounts.doctype.payment_entry.payment_entry import (
        get_default_bank_cash_account,
    )

    source = get_default_bank_cash_account(company, "Cash") or get_default_bank_cash_account(
        company, "Bank"
    )
    if not source or not source.get("account"):
        return None, _(
            "Configure a default Cash or Bank account on company {0} before raising a payment order."
        ).format(company)
    return source.get("account"), None


@frappe.whitelist(methods=["POST"])
def create_payment_order(contract: str, billing_period: str):
    """Create (or return) a draft Payment Entry (Pay/Supplier) for one billing period.

    Left in Draft — Apex posts no GL and never submits it.
    """
    from erpnext.accounts.party import get_party_account

    contract_doc = _load_eligible_contract(contract)
    _require_target(PAYMENT_ORDER_DOCTYPE)
    billing_period = _normalize_period(billing_period)

    frappe.db.get_value("Telecom Contract", contract_doc.name, "name", for_update=True)
    contract_doc.reload()

    existing = _existing_link(contract_doc, billing_period, PAYMENT_ORDER_DOCTYPE)
    if existing:
        return _result(PAYMENT_ORDER_DOCTYPE, existing, True)

    party_account = get_party_account("Supplier", contract_doc.supplier, contract_doc.company)
    paid_from, error = _company_paid_from(contract_doc.company)
    if error:
        frappe.throw(error)
    if not party_account:
        frappe.throw(
            _("Supplier {0} has no payable account for company {1}.").format(
                contract_doc.supplier, contract_doc.company
            )
        )

    period_end = _period_end(billing_period)
    pe = frappe.new_doc(PAYMENT_ORDER_DOCTYPE)
    pe.payment_type = "Pay"
    pe.company = contract_doc.company
    pe.posting_date = today()
    pe.party_type = "Supplier"
    pe.party = contract_doc.supplier
    pe.paid_from = paid_from
    pe.paid_to = party_account
    pe.paid_amount = contract_doc.recurring_amount
    pe.received_amount = contract_doc.recurring_amount
    pe.cost_center = contract_doc.cost_center
    pe.project = contract_doc.project
    pe.reference_no = contract_doc.name
    pe.reference_date = period_end
    pe.remarks = _("Telecom {0} — billing period {1} ({2}).").format(
        contract_doc.supplier, billing_period, contract_doc.name
    )
    # Prime the runtime party_account attribute before the manual set_missing_values():
    # validate() normally runs setup_party_account_field() first, but here
    # set_missing_values() is called pre-insert, so it must be initialised explicitly
    # (else ERPNext's set_missing_values raises AttributeError on self.party_account).
    pe.setup_party_account_field()
    pe.set_missing_values()
    pe.insert(ignore_permissions=True)  # audit-ok — create-permission enforced above

    _record_link(
        contract_doc,
        billing_period,
        PAYMENT_ORDER_DOCTYPE,
        pe.name,
        contract_doc.recurring_amount,
        contract_doc.currency,
    )
    return _result(PAYMENT_ORDER_DOCTYPE, pe.name, False)
