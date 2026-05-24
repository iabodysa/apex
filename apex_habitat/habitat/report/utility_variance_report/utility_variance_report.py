# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt


def execute(filters=None):
    columns = [
        {"label": frappe._("Bill"), "fieldname": "name", "fieldtype": "Link", "options": "Utility Bill Entry", "width": 150},
        {"label": frappe._("Utility Account"), "fieldname": "utility_account", "fieldtype": "Link", "options": "Utility Account", "width": 150},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 150},
        {"label": frappe._("Utility Type"), "fieldname": "utility_type", "fieldtype": "Data", "width": 110},
        {"label": frappe._("Amount (SAR)"), "fieldname": "bill_amount_sar", "fieldtype": "Currency", "width": 130},
        {"label": frappe._("Consumption"), "fieldname": "consumption_units", "fieldtype": "Float", "width": 110},
        {"label": frappe._("Variance from Avg (%)"), "fieldname": "variance_from_avg_pct", "fieldtype": "Percent", "width": 150},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
    ]

    query_filters = {"docstatus": 1}
    if filters and filters.get("building"):
        query_filters["building"] = filters["building"]

    rows = frappe.get_all(
        "Utility Bill Entry",
        filters=query_filters,
        fields=[
            "name",
            "utility_account",
            "building",
            "utility_type",
            "bill_amount_sar",
            "consumption_units",
            "variance_from_avg_pct",
            "status",
        ],
        order_by="variance_from_avg_pct desc",
        limit_page_length=1000,
    )

    data = []
    for row in rows:
        data.append({
            "name": row.name,
            "utility_account": row.utility_account,
            "building": row.building,
            "utility_type": row.utility_type,
            "bill_amount_sar": flt(row.get("bill_amount_sar")),
            "consumption_units": row.consumption_units,
            "variance_from_avg_pct": flt(row.get("variance_from_avg_pct")),
            "status": row.status,
        })
    return columns, data
