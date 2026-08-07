# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _

from apex.salis import permissions
from apex.apex_core.utils.report_summary import count_card, total_card


def execute(filters=None):
    """Returns the columns, rows and summary cards for the Fuel Exception Register report."""
    columns = [
        {"label": frappe._("Case"), "fieldname": "name", "fieldtype": "Link", "options": "Fuel Exception Case", "width": 180},
        {"label": frappe._("Exception Type"), "fieldname": "exception_type", "fieldtype": "Data", "width": 160},
        {"label": frappe._("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 160},
        {"label": frappe._("Driver"), "fieldname": "driver", "fieldtype": "Link", "options": "Salis Driver", "width": 180},
        {"label": frappe._("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 180},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Amount Recovered"), "fieldname": "amount_recovered", "fieldtype": "Currency", "width": 150},
        {"label": frappe._("Raised By"), "fieldname": "reported_by", "fieldtype": "Data", "width": 160},
        {"label": frappe._("Closed By"), "fieldname": "closed_by", "fieldtype": "Data", "width": 160},
    ]

    query_filters = {}
    if filters:
        for field in ("status", "exception_type"):
            if filters.get(field):
                query_filters[field] = filters[field]

        from_date = filters.get("from_date")
        to_date = filters.get("to_date")
        if from_date and to_date:
            query_filters["creation"] = ["between", [from_date, to_date]]
        elif from_date:
            query_filters["creation"] = [">=", from_date]
        elif to_date:
            query_filters["creation"] = ["<=", to_date]

    restrict, allowed = permissions.report_project_scope(frappe.session.user)
    if restrict:
        if not allowed:
            return columns, []
        query_filters["project"] = ["in", allowed]

    data = frappe.get_all(
        "Fuel Exception Case",
        filters=query_filters,
        fields=[
            "name",
            "exception_type",
            "vehicle",
            "driver",
            "project",
            "status",
            "amount_recovered",
            "reported_by",
            "closed_by",
            "creation",
        ],
        order_by="creation desc",
    )

    summary = [
        count_card(_("Exceptions"), data),
        total_card(_("Recovered"), data, "amount_recovered", "Currency", indicator="Green"),
    ]
    return columns, data, None, None, summary
