# Copyright (c) 2026, afmcoltd

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
    if not contract or not frappe.db.exists("Telecom Contract", {"name": contract}):
        frappe.throw(_("Telecom Contract {0} does not exist.").format(contract))
    doc = frappe.get_doc("Telecom Contract", contract)
    doc.check_permission("read")
    if doc.docstatus != 1:
        frappe.throw(_("Billing documents can only be raised from a submitted contract."))
    return doc


def _normalize_period(billing_period: str) -> str:
    period = (billing_period or "").strip()
    try:
        parsed = datetime.datetime.strptime(period, "%Y-%m")
    except ValueError:
        frappe.throw(_("Billing Period must look like 2026-07 (year and month)."))
    return parsed.strftime("%Y-%m")


def _period_end(billing_period: str):
    parsed = datetime.datetime.strptime(billing_period, "%Y-%m")
    last_day = calendar.monthrange(parsed.year, parsed.month)[1]
    return datetime.date(parsed.year, parsed.month, last_day)


def _existing_link(contract_doc, billing_period: str, document_type: str):
    for row in contract_doc.billing_documents or []:
        if row.billing_period == billing_period and row.document_type == document_type:
            if row.document_name and frappe.db.exists(document_type, {"name": row.document_name}):
                return row.document_name
    return None


def _record_link(contract_doc, billing_period, document_type, document_name, amount, currency):
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
    return {"document_type": document_type, "document_name": document_name, "existing": existing}


@frappe.whitelist(methods=["POST"])
def create_purchase_request(contract: str, billing_period: str):
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
    mr.insert()

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
    contract_doc = _load_eligible_contract(contract)
    return payable_allocation.list_payables(contract_doc.company, contract_doc.supplier)


@frappe.whitelist(methods=["POST"])
def create_payment_entry(contract: str, billing_period: str, purchase_invoice: str | None = None):
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
    pe.insert()

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
    existing = tuple(doc.get("ignore_linked_doctypes") or ())
    if CONTRACT_DOCTYPE not in existing:
        doc.ignore_linked_doctypes = (*existing, CONTRACT_DOCTYPE)
