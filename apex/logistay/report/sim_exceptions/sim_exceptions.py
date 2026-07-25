# Copyright (c) 2026, AFMCO and contributors
"""SIM Exceptions: SIMs that need attention (suspended, lost, assigned without a
cost center, or missing an ICCID), company-scoped."""

import frappe

from apex.logistay import permissions


def execute(filters=None):
    filters = filters or {}
    columns = [
        {"label": frappe._("Mobile Number"), "fieldname": "mobile_number", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": frappe._("Exception"), "fieldname": "exception", "fieldtype": "Data", "width": 260},
        {"label": frappe._("Contract"), "fieldname": "telecom_contract", "fieldtype": "Link", "options": "Telecom Contract", "width": 170},
        {"label": frappe._("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 140},
    ]

    query = {}
    if filters.get("company"):
        query["company"] = filters["company"]

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
        "SIM Card",
        filters=query,
        fields=[
            "mobile_number",
            "status",
            "current_custodian_type",
            "current_cost_center",
            "iccid",
            "telecom_contract",
            "supplier",
        ],
    )
    data = []
    for row in rows:
        issues = []
        if row.status in ("Suspended", "Lost"):
            issues.append(frappe._(row.status))
        if row.status == "Assigned" and not row.current_cost_center:
            issues.append(frappe._("Assigned without a cost center"))
        if not row.iccid:
            issues.append(frappe._("Missing ICCID"))
        if issues:
            data.append(
                {
                    "mobile_number": row.mobile_number,
                    "status": row.status,
                    "exception": ", ".join(issues),
                    "telecom_contract": row.telecom_contract,
                    "supplier": row.supplier,
                }
            )
    return columns, data
