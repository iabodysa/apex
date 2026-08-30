# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _

from apex.apex_core.utils.report_helpers import date_range_condition
from apex.apex_core.utils.report_summary import count_card, total_card


def execute(filters=None):
    columns = [
        {"label": frappe._("Payment"), "fieldname": "name", "fieldtype": "Link", "options": "Salis Payment Request", "width": 180},
        {"label": frappe._("Expense Type"), "fieldname": "expense_type", "fieldtype": "Data", "width": 150},
        {"label": frappe._("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 130},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 160},
        {"label": frappe._("Cost Center"), "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 160},
        {"label": frappe._("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 180},
        {"label": frappe._("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 180},
        {"label": frappe._("Requested By"), "fieldname": "requested_by", "fieldtype": "Data", "width": 160},
        {"label": frappe._("Finance Approved By"), "fieldname": "finance_approved_by", "fieldtype": "Data", "width": 160},
    ]

    query_filters = {}
    if filters:
        for field in ("status", "expense_type", "company", "cost_center", "project"):
            if filters.get(field):
                query_filters[field] = filters[field]
        date_condition = date_range_condition(filters, "creation")
        if date_condition is not None:
            query_filters["creation"] = date_condition

    data = frappe.get_list(
        "Salis Payment Request",
        filters=query_filters,
        fields=[
            "name",
            "expense_type",
            "amount",
            "status",
            "company",
            "cost_center",
            "supplier",
            "project",
            "requested_by",
            "finance_approved_by",
            "creation",
        ],
        order_by="creation desc",
    )

    summary = [
        count_card(_("Payments"), data),
        total_card(_("Total Amount"), data, "amount", "Currency"),
    ]
    return columns, data, None, None, summary
