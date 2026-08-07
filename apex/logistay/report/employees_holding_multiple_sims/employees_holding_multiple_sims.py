# Copyright (c) 2026, afmcoltd
"""Employees currently holding more than one SIM, company-scoped."""

import frappe
from frappe import _

from apex.logistay import permissions
from apex.apex_core.utils.report_summary import count_card, total_card


def execute(filters=None):
    """Lists employees currently holding more than one SIM Card, scoped to the caller's companies."""
    filters = filters or {}
    columns = [
        {"label": frappe._("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 160},
        {"label": frappe._("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": frappe._("SIM Count"), "fieldname": "sim_count", "fieldtype": "Int", "width": 100},
        {"label": frappe._("Mobile Numbers"), "fieldname": "mobile_numbers", "fieldtype": "Data", "width": 320},
    ]

    query = {"current_custodian_type": "Employee", "current_custodian_employee": ["is", "set"]}
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
        "SIM Card", filters=query, fields=["current_custodian_employee", "mobile_number"]
    )
    holdings = {}
    for row in rows:
        holdings.setdefault(row.current_custodian_employee, []).append(row.mobile_number)
    multiple = {emp: mobiles for emp, mobiles in holdings.items() if len(mobiles) > 1}

    names = {}
    if multiple:
        names = {
            e.name: e.employee_name
            for e in frappe.get_all(
                "Employee", filters={"name": ["in", list(multiple)]}, fields=["name", "employee_name"]
            )
        }

    data = [
        {
            "employee": emp,
            "employee_name": names.get(emp),
            "sim_count": len(mobiles),
            "mobile_numbers": ", ".join(sorted(m for m in mobiles if m)),
        }
        for emp, mobiles in sorted(multiple.items(), key=lambda kv: len(kv[1]), reverse=True)
    ]
    summary = [
        count_card(_("Employees"), data),
        total_card(_("SIMs Held"), data, "sim_count", "Int", indicator="Orange"),
    ]
    return columns, data, None, None, summary
