# Copyright (c) 2026, AFMCO and contributors

"""Maintenance engine for the Habitat module.

Posts the immutable Maintenance Cost Ledger, mirroring the Salis fuel/rental
engine pattern (``apex.salis.fuel_engine``) and the Habitat no-GL,
system-written ledger idiom (``accommodation_ledger``).

A completed Maintenance Work Order posts one Maintenance Cost Ledger row per
procurement item (``Maintenance Procurement Item.estimated_cost``). Posting is
idempotent on ``(source_doctype, source_name, source_detail_no)`` so re-running
completion never double-posts. Cancelling the Work Order reverses each posted
row with a negative mirror row (``reversal_of`` set, ``is_cancelled`` flagged) —
never a delete — so a historical cost query stays stable.

No GL is written; these are operational memos used for maintenance-spend
reporting that does not shift when a Work Order is later cancelled. Cost is read
from the procurement child ``estimated_cost`` (the Work Order's own costing
field; there is no ``amount`` field on the child).
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, now_datetime, today

from apex.apex_core.utils.company import resolve_company

LEDGER_DOCTYPE = "Maintenance Cost Ledger"
SOURCE_DOCTYPE = "Maintenance Work Order"


def _ledger_row_exists(source_name: str, detail_no: int) -> bool:
    """True if an ORIGINAL ledger row already exists for this Work Order + item
    row (idempotency key). Reversal rows carry reversal_of, so an original is
    keyed by reversal_of unset."""
    return bool(
        frappe.db.exists(
            LEDGER_DOCTYPE,
            {
                "source_doctype": SOURCE_DOCTYPE,
                "source_name": source_name,
                "source_detail_no": detail_no,
                "reversal_of": ["is", "not set"],
            },
        )
    )


def _insert_ledger_row(
    work_order,
    company: str | None,
    row,
    detail_no: int,
) -> None:
    """Insert one Maintenance Cost Ledger row for a procurement item.

    Source traceability: ``source_doctype`` is the Work Order DocType, ``source_name``
    the Work Order name, and ``source_detail_no`` the 1-based procurement row idx, so
    each item posts a distinct, idempotency-keyed row.
    """
    frappe.get_doc(
        {
            "doctype": LEDGER_DOCTYPE,
            "company": company,
            "posting_date": work_order.actual_end_date or today(),
            "maintenance_work_order": work_order.name,
            "maintenance_request": work_order.maintenance_request,
            "building": work_order.building,
            "item": row.get("item"),
            "material": row.get("material"),
            "item_description": row.get("item_description"),
            "amount": flt(row.get("estimated_cost") or 0),
            "logged_at": now_datetime(),
            "source_doctype": SOURCE_DOCTYPE,
            "source_name": work_order.name,
            "source_detail_no": detail_no,
        }
    ).insert(ignore_permissions=True)  # audit-ok — system ledger memo on completion


def post_maintenance_cost(work_order) -> int:
    """Post one Maintenance Cost Ledger row per procurement item of a completed
    Work Order. Returns the number of rows posted.

    Idempotent on ``(source_doctype, source_name, source_detail_no)``: an item
    already ledgered is skipped, so re-running completion posts nothing new. Rows
    with a zero/blank estimated cost are skipped (no zero-amount memo).
    """
    # Work Order carries no company field -> module default chain (reference only).
    company = resolve_company("Habitat")
    posted = 0
    for detail_no, row in enumerate(work_order.procurement_items or [], start=1):
        amount = flt(row.get("estimated_cost") or 0)
        if amount <= 0:
            continue
        if _ledger_row_exists(work_order.name, detail_no):
            continue
        _insert_ledger_row(work_order, company, row, detail_no)
        posted += 1
    return posted


def reverse_maintenance_cost(source_name: str) -> int:
    """Reverse the ledgered cost for a cancelled Work Order.

    Posts a negative mirror row for each ORIGINAL ledger row of the Work Order —
    negating ``amount``, flagging ``is_cancelled``, linking back via ``reversal_of``
    — so the Work Order nets to zero in every cost sum while the original row is
    preserved for audit. Mirrors the fuel-engine reversal idiom: a negated row
    with reversal_of set, not a delete.

    Idempotent: calling it twice posts at most one reversal per original row (an
    original that already has a reversal pointing at it is skipped). Returns the
    number of reversal rows posted.
    """
    originals = frappe.get_all(
        LEDGER_DOCTYPE,
        filters={
            "source_doctype": SOURCE_DOCTYPE,
            "source_name": source_name,
            "reversal_of": ["is", "not set"],
        },
        fields=[
            "name",
            "company",
            "posting_date",
            "maintenance_work_order",
            "maintenance_request",
            "building",
            "item",
            "material",
            "item_description",
            "amount",
            "source_detail_no",
        ],
    )

    posted = 0
    for orig in originals:
        if frappe.db.exists(LEDGER_DOCTYPE, {"reversal_of": orig.name}):
            continue
        frappe.get_doc(
            {
                "doctype": LEDGER_DOCTYPE,
                "company": orig.company,
                "posting_date": today(),
                "maintenance_work_order": orig.maintenance_work_order,
                "maintenance_request": orig.maintenance_request,
                "building": orig.building,
                "item": orig.item,
                "material": orig.material,
                "item_description": orig.item_description,
                "amount": -flt(orig.amount),
                "is_cancelled": 1,
                "logged_at": now_datetime(),
                "source_doctype": SOURCE_DOCTYPE,
                "source_name": source_name,
                "source_detail_no": orig.source_detail_no,
                "reversal_of": orig.name,
            }
        ).insert(ignore_permissions=True)  # audit-ok — reversing a system memo this Work Order posted
        posted += 1

    return posted
