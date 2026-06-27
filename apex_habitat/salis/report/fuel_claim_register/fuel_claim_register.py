# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

"""Fuel Claim Register report.

ORM listing of Fuel Claim records with their claimed vs consumed litres and the
reconciliation variance, by project / vehicle / period / status.
"""

import frappe
from frappe import _

from apex_habitat.salis import permissions


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Claim"), "fieldname": "name", "fieldtype": "Link", "options": "Fuel Claim", "width": 130},
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
        {"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 160},
        {"label": _("Period"), "fieldname": "period_month", "fieldtype": "Data", "width": 100},
        {"label": _("Claimed Litres"), "fieldname": "claimed_litres", "fieldtype": "Float", "width": 120},
        {"label": _("Consumed Litres"), "fieldname": "consumed_litres", "fieldtype": "Float", "width": 130},
        {"label": _("Variance (L)"), "fieldname": "variance_litres", "fieldtype": "Float", "width": 120},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 150},
    ]

    query_filters = {}
    if filters.get("project"):
        query_filters["project"] = filters["project"]
    if filters.get("vehicle"):
        query_filters["vehicle"] = filters["vehicle"]
    if filters.get("period_month"):
        query_filters["period_month"] = filters["period_month"]
    if filters.get("status"):
        query_filters["status"] = filters["status"]

    # get_all forces ignore_permissions, bypassing the project row-scoping the desk
    # list gets via permission_query_conditions; re-apply the caller's project scope
    # (Fuel Claim carries a direct project); oversight roles see all.
    restrict, allowed = permissions.report_project_scope(frappe.session.user)
    if restrict:
        chosen = query_filters.get("project")
        if not allowed or (chosen and chosen not in allowed):
            return columns, []
        if not chosen:
            query_filters["project"] = ["in", allowed]

    data = frappe.get_all(
        "Fuel Claim",
        filters=query_filters,
        fields=[
            "name",
            "project",
            "vehicle",
            "period_month",
            "claimed_litres",
            "consumed_litres",
            "variance_litres",
            "status",
        ],
        order_by="period_month desc, vehicle asc",
    )

    return columns, data
