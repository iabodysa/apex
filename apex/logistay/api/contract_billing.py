# Copyright (c) 2026, AFMCO and contributors
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
from frappe.utils import getdate, today

from apex.apex_core.utils import payable_allocation

CONTRACT_DOCTYPE = "Telecom Contract"
PURCHASE_REQUEST_DOCTYPE = "Material Request"
PAYMENT_ENTRY_DOCTYPE = payable_allocation.PAYMENT_ENTRY_DOCTYPE




def _load_eligible_contract(contract: str):
    """Return the submitted Telecom Contract the caller may read, or throw.

    ``contract`` arrives from a whitelisted endpoint, so the existence probe filters
    on ``name``: the positional form answers the value back without querying when it
    equals the DocType (database.py:1259), letting the literal string "Telecom
    Contract" clear this gate and reach ``get_doc`` — which raises a bare framework
    404 instead of the named refusal below. Permission checking is unaffected; what
    the short-circuit costs is this function's own message.
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

    The probe filters on ``name`` rather than passing the recorded value positionally:
    ``frappe.db.exists(dt, dn)`` answers ``dn`` back WITHOUT touching the database when
    the two are equal (database.py:1259), so a logged name of "Payment Entry" would be
    reported as a live draft on the strength of the string alone. The Dynamic Link on
    the billing row makes that pair hard to persist today, so this is the guard
    refusing to depend on a neighbouring layer for its own correctness rather than a
    live defect — duplicate-safety is this function's whole job.
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
    contract_doc.save(ignore_permissions=True)  # audit-ok — append-only billing log


def _result(document_type, document_name, existing):
    return {"document_type": document_type, "document_name": document_name, "existing": existing}




@frappe.whitelist(methods=["POST"])
def create_purchase_request(contract: str, billing_period: str):
    """Create (or return) a draft Material Request (Purchase) for one billing period."""
    contract_doc = _load_eligible_contract(contract)
    payable_allocation.require_target(PURCHASE_REQUEST_DOCTYPE)
    billing_period = _normalize_period(billing_period)

    if not contract_doc.service_item:
        frappe.throw(
            _("Set a Service Item on the contract before raising a purchase request.")
        )

    frappe.db.get_value("Telecom Contract", contract_doc.name, "name", for_update=True)
    contract_doc.reload()

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
    payable_allocation.require_target(PAYMENT_ENTRY_DOCTYPE)
    billing_period = _normalize_period(billing_period)

    frappe.db.get_value("Telecom Contract", contract_doc.name, "name", for_update=True)
    contract_doc.reload()

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
    pe.insert(ignore_permissions=True)  # audit-ok — create-permission enforced above

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

    The billing table's ``document_name`` is a Dynamic Link, so a SUBMITTED contract
    citing a payment makes ``check_no_back_links_exist`` raise LinkExistsError and
    Accounts can never cancel (delete_doc.py:396-404). Telecom operations only RECORD
    which payment settled a period; they do not own its lifecycle, and an operational
    record must not veto the accounting ledger.

    The native release valve is the doc-level ``ignore_linked_doctypes`` read at
    delete_doc.py:403, which is guarded by ``method == "Cancel"`` — so DELETING a cited
    payment stays blocked and the billing row can never point at nothing. That
    method guard is why this is used instead of the ``ignore_links_on_delete`` hook,
    whose branches (delete_doc.py:277 and :402) carry no such condition and would also
    unblock deleting the contract's Supplier, Company, Cost Center, Project and Item.

    ERPNext sets this same attribute for its own ledgers in ``PaymentEntry.on_cancel``,
    which runs before this handler and before the link check (document.py:1185-1186);
    appending rather than assigning is what keeps those ledger entries intact.
    """
    existing = tuple(doc.get("ignore_linked_doctypes") or ())
    if CONTRACT_DOCTYPE not in existing:
        doc.ignore_linked_doctypes = (*existing, CONTRACT_DOCTYPE)
