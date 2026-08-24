# Copyright (c) 2026, afmcoltd


from __future__ import annotations

import frappe
from frappe.utils import flt, now_datetime, today

from apex.apex_core.utils.company import resolve_company


LEDGER_DOCTYPE = "Maintenance Cost Ledger"
SOURCE_DOCTYPE = "Maintenance Work Order"


def post_maintenance_cost(work_order) -> int:
    company = resolve_company("Habitat")
    posted = 0
    for detail_no, row in enumerate(work_order.procurement_items or [], start=1):
        amount = flt(row.get("estimated_cost") or 0)
        if amount <= 0:
            continue
        if frappe.db.exists(
            LEDGER_DOCTYPE,
            {
                "source_doctype": SOURCE_DOCTYPE,
                "source_name": work_order.name,
                "source_detail_no": detail_no,
                "reversal_of": ["is", "not set"],
            },
        ):
            continue
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
                "amount": amount,
                "logged_at": now_datetime(),
                "source_doctype": SOURCE_DOCTYPE,
                "source_name": work_order.name,
                "source_detail_no": detail_no,
            }
        ).insert(ignore_permissions=True)
        posted += 1
    return posted


def reverse_maintenance_cost(source_name: str) -> int:
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
        ).insert(ignore_permissions=True)
        posted += 1

    return posted
