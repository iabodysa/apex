# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

"""Fuel Claim Register report.

ORM listing of Fuel Claim records with their claimed vs consumed litres and the
reconciliation variance, by project / vehicle / period / status (governance
G10/G22).
"""

import frappe
from frappe import _


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
