# Copyright (c) 2026, AFMCO and contributors
"""SIM counts grouped by supplier and contract, company-scoped."""

import frappe

from apex.sim_operations import permissions


def execute(filters=None):
    filters = filters or {}
    columns = [
        {"label": frappe._("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
        {"label": frappe._("Contract"), "fieldname": "telecom_contract", "fieldtype": "Link", "options": "Telecom Contract", "width": 180},
        {"label": frappe._("Total SIMs"), "fieldname": "sim_count", "fieldtype": "Int", "width": 110},
        {"label": frappe._("Assigned"), "fieldname": "assigned_count", "fieldtype": "Int", "width": 110},
    ]

    query = {}
    if filters.get("company"):
        query["company"] = filters["company"]
    if filters.get("supplier"):
        query["supplier"] = filters["supplier"]

    restrict, allowed = permissions.report_company_scope(frappe.session.user)
    if restrict:
        if not allowed:
            return columns, []
        chosen = query.get("company")
        if chosen and chosen not in allowed:
            return columns, []
        if not chosen:
            query["company"] = ["in", allowed]

    rows = frappe.get_all(
        "SIM Card", filters=query, fields=["supplier", "telecom_contract", "status"]
    )
    agg = {}
    for row in rows:
        key = (row.supplier, row.telecom_contract)
        bucket = agg.setdefault(key, {"total": 0, "assigned": 0})
        bucket["total"] += 1
        if row.status == "Assigned":
            bucket["assigned"] += 1

    data = [
        {
            "supplier": supplier,
            "telecom_contract": contract,
            "sim_count": bucket["total"],
            "assigned_count": bucket["assigned"],
        }
        for (supplier, contract), bucket in sorted(
            agg.items(), key=lambda kv: kv[1]["total"], reverse=True
        )
    ]
    return columns, data
