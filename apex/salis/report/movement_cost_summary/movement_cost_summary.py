# Copyright (c) 2026, AFMCO and contributors

import frappe
from frappe import _
from frappe.utils import flt

from apex.apex_core.utils.report_helpers import date_range_condition
from apex.apex_core.utils.report_summary import percent_card, total_card


def execute(filters=None):
    columns = [
        {"label": frappe._("Recovery Type"), "fieldname": "recovery_type", "fieldtype": "Data", "width": 200},
        {"label": frappe._("Count"), "fieldname": "count", "fieldtype": "Int", "width": 110},
        {"label": frappe._("Total Amount"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 160},
        {"label": frappe._("Total Recovered"), "fieldname": "total_recovered", "fieldtype": "Currency", "width": 160},
    ]

    query_filters = {}
    if filters:
        if filters.get("status"):
            query_filters["status"] = filters["status"]
        if filters.get("company"):
            query_filters["company"] = filters["company"]
        if filters.get("cost_center"):
            query_filters["cost_center"] = filters["cost_center"]
        date_condition = date_range_condition(filters, "request_date")
        if date_condition is not None:
            query_filters["request_date"] = date_condition

    records = frappe.get_all(
        "Movement Cost Recovery",
        filters=query_filters,
        fields=["recovery_type", "amount", "status"],
    )

    summary = {}
    for row in records:
        rtype = row.get("recovery_type") or frappe._("Unspecified")
        bucket = summary.setdefault(
            rtype,
            {"recovery_type": rtype, "count": 0, "total_amount": 0.0, "total_recovered": 0.0},
        )
        bucket["count"] += 1
        amount = row.get("amount") or 0.0
        bucket["total_amount"] += amount
        if row.get("status") == "Recovered":
            bucket["total_recovered"] += amount

    data = sorted(summary.values(), key=lambda b: b["recovery_type"])

    total = sum(flt(r.get("total_amount")) for r in data)
    recovered = sum(flt(r.get("total_recovered")) for r in data)
    summary = [
        total_card(_("Recoveries"), data, "count", "Int"),
        total_card(_("Total Amount"), data, "total_amount", "Currency"),
        total_card(_("Recovered"), data, "total_recovered", "Currency", indicator="Green"),
        percent_card(_("Recovered Share"), recovered, total),
    ]
    return columns, data, None, None, summary
