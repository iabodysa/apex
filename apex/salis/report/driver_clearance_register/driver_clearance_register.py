# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _

from apex.apex_core.utils.report_summary import count_card


def execute(filters=None):
    columns = [
        {"label": frappe._("Clearance"), "fieldname": "name", "fieldtype": "Link", "options": "Driver Clearance", "width": 180},
        {"label": frappe._("Driver"), "fieldname": "driver", "fieldtype": "Link", "options": "Salis Driver", "width": 200},
        {"label": frappe._("Clearance Reason"), "fieldname": "clearance_reason", "fieldtype": "Data", "width": 160},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
        {"label": frappe._("Outstanding Fuel Exceptions"), "fieldname": "outstanding_fuel_exceptions", "fieldtype": "Int", "width": 200},
        {"label": frappe._("Outstanding Recoveries"), "fieldname": "outstanding_recoveries", "fieldtype": "Int", "width": 180},
    ]

    query_filters = {}
    if filters:
        for field in ("status", "clearance_reason", "driver"):
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

    data = frappe.get_list(
        "Driver Clearance",
        filters=query_filters,
        fields=[
            "name",
            "driver",
            "clearance_reason",
            "status",
            "outstanding_fuel_exceptions",
            "outstanding_recoveries",
            "creation",
        ],
        order_by="creation desc",
    )

    summary = [
        count_card(_("Drivers"), data),
        count_card(
            _("Blocked by Outstanding Items"),
            data,
            lambda r: (r.get("outstanding_fuel_exceptions") or 0)
            or (r.get("outstanding_recoveries") or 0),
            "Red",
        ),
    ]
    return columns, data, None, None, summary
