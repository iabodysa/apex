# Copyright (c) 2026, afmcoltd

"""Goods Receipt Register — what entered each building store, from whom, and whether
it reached handover.

The rows are ITEM rows, not documents: a receipt of five article lines where one is
still sitting un-handed-over is one document and five lines, and rolling it up to the
document would hide the line that matters. Only submitted receipts are listed — a
draft has not arrived yet, and a cancelled receipt is out with docstatus 2.

Scoped by intake building through the same resolver the permission hook uses, so a
scope correction reaches this report and the desk list together.
"""

import frappe
from frappe import _

from apex.apex_core.utils.report_summary import count_card, percent_card
from apex.habitat import permissions


def execute(filters=None):
    """Returns the columns, line rows and summary cards for the Goods Receipt Register report."""
    filters = filters or {}
    columns = get_columns()

    query_filters = {"docstatus": 1}
    if filters.get("building"):
        query_filters["intake_building"] = filters["building"]
    if filters.get("status"):
        query_filters["status"] = filters["status"]
    if filters.get("from_date") and filters.get("to_date"):
        query_filters["receipt_date"] = ["between", [filters["from_date"], filters["to_date"]]]
    elif filters.get("from_date"):
        query_filters["receipt_date"] = [">=", filters["from_date"]]
    elif filters.get("to_date"):
        query_filters["receipt_date"] = ["<=", filters["to_date"]]

    restrict, allowed = permissions.report_building_scope(frappe.session.user, doctype="Goods Receipt")
    if restrict:
        chosen = query_filters.get("intake_building")
        if not allowed or (chosen and chosen not in allowed):
            return columns, [], None, None, get_report_summary([])
        if not chosen:
            query_filters["intake_building"] = ["in", allowed]

    receipts = frappe.get_all(
        "Goods Receipt",
        filters=query_filters,
        fields=[
            "name",
            "receipt_date",
            "intake_building",
            "status",
            "supplier_name",
            "external_reference",
        ],
        order_by="receipt_date desc",
    )
    if not receipts:
        return columns, [], None, None, get_report_summary([])

    lines = frappe.get_all(
        "Material Transfer Item",
        filters={"parent": ["in", [r.name for r in receipts]], "parenttype": "Goods Receipt"},
        fields=["parent", "item_type", "item", "item_name", "qty", "uom"],
        order_by="parent asc, idx asc",
    )
    if filters.get("item_type"):
        lines = [line for line in lines if line.item_type == filters["item_type"]]
    by_name = {r.name: r for r in receipts}

    data = []
    for line in lines:
        header = by_name.get(line.parent)
        if not header:
            continue
        data.append(
            {
                "name": line.parent,
                "receipt_date": header.receipt_date,
                "building": header.intake_building,
                "status": header.status,
                "supplier_name": header.supplier_name,
                "external_reference": header.external_reference,
                "item_type": line.item_type,
                "item": line.item,
                "item_name": line.item_name,
                "qty": line.qty,
                "uom": line.uom,
            }
        )

    return columns, data, None, None, get_report_summary(data)


def get_report_summary(data):
    """Builds summary cards for receipt line count, receipt count and percent handed over."""
    receipts = {r.get("name") for r in data if r.get("name")}
    awaiting = [r for r in data if r.get("status") == "Received"]
    handed = len(data) - len(awaiting)
    return [
        count_card(_("Receipt Lines"), data),
        count_card(_("Receipts"), [{"n": n} for n in receipts]),
        count_card(_("Awaiting Handover"), awaiting, indicator="Orange" if awaiting else None),
        percent_card(_("Handed Over"), handed, len(data)),
    ]


def get_columns():
    """Returns the column definitions for the Goods Receipt Register report."""
    return [
        {"label": _("Receipt"), "fieldname": "name", "fieldtype": "Link", "options": "Goods Receipt", "width": 170},
        {"label": _("Receipt Date"), "fieldname": "receipt_date", "fieldtype": "Date", "width": 110},
        {"label": _("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 150},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
        {"label": _("Supplier"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 150},
        {"label": _("External Reference"), "fieldname": "external_reference", "fieldtype": "Data", "width": 130},
        {"label": _("Item Type"), "fieldname": "item_type", "fieldtype": "Data", "width": 130},
        {"label": _("Item"), "fieldname": "item", "fieldtype": "Dynamic Link", "options": "item_type", "width": 150},
        {"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
        {"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 80},
        {"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 80},
    ]
