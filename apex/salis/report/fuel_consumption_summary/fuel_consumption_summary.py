# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

import frappe

from apex.apex_core.utils.report_helpers import date_range_condition, scoped_names
from apex.salis import permissions


def execute(filters=None):
    columns = [
        {"label": frappe._("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 180},
        {"label": frappe._("Total Litres"), "fieldname": "total_litres", "fieldtype": "Float", "width": 130},
        {"label": frappe._("Total Amount"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 150},
        {"label": frappe._("Log Count"), "fieldname": "log_count", "fieldtype": "Int", "width": 110},
    ]

    log_filters = {}
    if filters:
        date_condition = date_range_condition(filters, "log_date")
        if date_condition is not None:
            log_filters["log_date"] = date_condition

    # [#be5q0w]
    restrict, allowed = permissions.report_project_scope(frappe.session.user)
    if restrict:
        if not allowed:
            return columns, []
        in_scope_vehicles = scoped_names("Salis Vehicle", allowed)
        if not in_scope_vehicles:
            return columns, []
        log_filters["vehicle"] = ["in", in_scope_vehicles]

    logs = frappe.get_all(
        "Fuel Daily Log",
        filters=log_filters,
        fields=["vehicle", "litres", "amount"],
    )

    summary = {}
    for log in logs:
        vehicle = log.vehicle or ""
        row = summary.setdefault(vehicle, {"vehicle": vehicle, "total_litres": 0.0, "total_amount": 0.0, "log_count": 0})
        row["total_litres"] += log.litres or 0
        row["total_amount"] += log.amount or 0
        row["log_count"] += 1

    data = sorted(summary.values(), key=lambda row: row["vehicle"])

    return columns, data
