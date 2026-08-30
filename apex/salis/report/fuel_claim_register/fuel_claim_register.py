# Copyright (c) 2026, afmcoltd


import frappe
from frappe import _
from frappe.utils import flt

from apex.apex_core.utils.report_summary import count_card, total_card


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

    data = frappe.get_list(
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

    summary = [
        count_card(_("Claims"), data),
        total_card(_("Claimed Litres"), data, "claimed_litres"),
        total_card(_("Consumed Litres"), data, "consumed_litres"),
        total_card(
            _("Variance (L)"),
            data,
            "variance_litres",
            indicator="Red" if sum(flt(r.get("variance_litres")) for r in data) < 0 else "Green",
        ),
    ]
    return columns, data, None, None, summary
