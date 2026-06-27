# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

import frappe

from apex_habitat.salis import permissions


def execute(filters=None):
    columns = [
        {"label": frappe._("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 180},
        {"label": frappe._("Total Litres"), "fieldname": "total_litres", "fieldtype": "Float", "width": 130},
        {"label": frappe._("Total Amount"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 150},
        {"label": frappe._("Log Count"), "fieldname": "log_count", "fieldtype": "Int", "width": 110},
    ]

    log_filters = {}
    if filters:
        if filters.get("from_date") and filters.get("to_date"):
            log_filters["log_date"] = ["between", [filters["from_date"], filters["to_date"]]]
        elif filters.get("from_date"):
            log_filters["log_date"] = [">=", filters["from_date"]]
        elif filters.get("to_date"):
            log_filters["log_date"] = ["<=", filters["to_date"]]

    # get_all forces ignore_permissions, bypassing the project row-scoping the desk
    # list gets via permission_query_conditions. Fuel Daily Log has no own project —
    # it reaches one through its vehicle — so confine the logs to the vehicles in the
    # caller's allowed projects; oversight roles see all.
    user = frappe.session.user
    if not permissions._is_unscoped(user):
        allowed = permissions._allowed_projects(user)
        if not allowed:
            return columns, []
        in_scope_vehicles = frappe.get_all(
            "Salis Vehicle",
            filters={"project": ["in", allowed]},
            pluck="name",
        )
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
