# Copyright (c) 2026, AFMCO and contributors

import frappe
from frappe import _

from apex.apex_core.utils.report_helpers import date_range_condition
from apex.apex_core.utils.report_summary import count_card, total_card


def execute(filters=None):
    columns = [
        {"label": _("Recovery"), "fieldname": "name", "fieldtype": "Link", "options": "Movement Cost Recovery", "width": 180},
        {"label": _("Recovery Type"), "fieldname": "recovery_type", "fieldtype": "Data", "width": 150},
        {"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 150},
        {"label": _("Driver"), "fieldname": "driver", "fieldtype": "Link", "options": "Salis Driver", "width": 150},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150},
        {"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 130},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
        {"label": _("Payment Request"), "fieldname": "payment_request", "fieldtype": "Link", "options": "Salis Payment Request", "width": 180},
    ]

    query_filters = {}
    if filters:
        for field in ("status", "recovery_type", "vehicle", "driver", "employee", "company", "cost_center"):
            if filters.get(field):
                query_filters[field] = filters[field]
        date_condition = date_range_condition(filters, "creation")
        if date_condition is not None:
            query_filters["creation"] = date_condition

    data = frappe.get_all(
        "Movement Cost Recovery",
        filters=query_filters,
        fields=[
            "name",
            "recovery_type",
            "vehicle",
            "driver",
            "employee",
            "amount",
            "status",
            "payment_request",
            "creation",
        ],
        order_by="creation desc",
    )

    summary = [
        count_card(_("Recoveries"), data),
        total_card(_("Total Amount"), data, "amount", "Currency"),
    ]
    return columns, data, None, None, summary
