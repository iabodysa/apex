# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": frappe._("Movement"), "fieldname": "name", "fieldtype": "Link", "options": "Facility Asset Movement", "width": 160},
        {"label": frappe._("Date"), "fieldname": "movement_date", "fieldtype": "Date", "width": 110},
        {"label": frappe._("Category"), "fieldname": "movement_category", "fieldtype": "Data", "width": 160},
        {"label": frappe._("Asset"), "fieldname": "facility_asset", "fieldtype": "Link", "options": "Facility Asset", "width": 150},
        {"label": frappe._("From Building"), "fieldname": "from_building", "fieldtype": "Link", "options": "Accommodation Building", "width": 150},
        {"label": frappe._("From Company"), "fieldname": "from_company", "fieldtype": "Link", "options": "Company", "width": 140},
        {"label": frappe._("To Building"), "fieldname": "to_building", "fieldtype": "Link", "options": "Accommodation Building", "width": 150},
        {"label": frappe._("To Company"), "fieldname": "to_company", "fieldtype": "Link", "options": "Company", "width": 140},
        {"label": frappe._("Release Approved"), "fieldname": "release_approved_by", "fieldtype": "Link", "options": "User", "width": 140},
        {"label": frappe._("Receiving Confirmed"), "fieldname": "receiving_confirmed_by", "fieldtype": "Link", "options": "User", "width": 150},
        {"label": frappe._("Accounting Acknowledged"), "fieldname": "accounting_acknowledged", "fieldtype": "Check", "width": 150},
        {"label": frappe._("Gate Pass"), "fieldname": "gate_pass_reference", "fieldtype": "Data", "width": 120},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
    ]

    query_filters = {"is_intercompany": 1}
    if filters.get("from_company"):
        query_filters["from_company"] = filters["from_company"]
    if filters.get("to_company"):
        query_filters["to_company"] = filters["to_company"]
    if filters.get("from_date") and filters.get("to_date"):
        query_filters["movement_date"] = ["between", [filters["from_date"], filters["to_date"]]]
    elif filters.get("from_date"):
        query_filters["movement_date"] = [">=", filters["from_date"]]
    elif filters.get("to_date"):
        query_filters["movement_date"] = ["<=", filters["to_date"]]
    if filters.get("accounting_acknowledged") is not None:
        query_filters["accounting_acknowledged"] = filters["accounting_acknowledged"]

    rows = frappe.get_all(
        "Facility Asset Movement",
        filters=query_filters,
        fields=[
            "name", "movement_date", "movement_category", "facility_asset",
            "from_building", "from_company", "to_building", "to_company",
            "release_approved_by", "receiving_confirmed_by",
            "accounting_acknowledged", "gate_pass_reference", "docstatus",
        ],
        order_by="movement_date desc",
    )

    data = []
    for row in rows:
        status = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(row.docstatus, "")
        data.append({
            "name": row.name,
            "movement_date": row.movement_date,
            "movement_category": row.movement_category or "",
            "facility_asset": row.facility_asset,
            "from_building": row.from_building or "",
            "from_company": row.from_company or "",
            "to_building": row.to_building,
            "to_company": row.to_company or "",
            "release_approved_by": row.release_approved_by or "",
            "receiving_confirmed_by": row.receiving_confirmed_by or "",
            "accounting_acknowledged": row.accounting_acknowledged or 0,
            "gate_pass_reference": row.gate_pass_reference or "",
            "status": status,
        })

    return columns, data
