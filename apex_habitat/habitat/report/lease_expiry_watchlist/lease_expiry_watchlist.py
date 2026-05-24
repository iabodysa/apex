# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import date_diff, today, flt


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": frappe._("Lease"), "fieldname": "name", "fieldtype": "Link", "options": "Accommodation Lease", "width": 150},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 160},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": frappe._("Lease End Date"), "fieldname": "lease_end_date", "fieldtype": "Date", "width": 120},
        {"label": frappe._("Days to Expiry"), "fieldname": "days_to_expiry", "fieldtype": "Int", "width": 120},
        {"label": frappe._("Monthly Rent (SAR)"), "fieldname": "rent_amount", "fieldtype": "Currency", "width": 140},
    ]

    query_filters = {"docstatus": 1, "status": "Active"}
    if filters.get("building"):
        query_filters["building"] = filters["building"]
    if filters.get("from_date") and filters.get("to_date"):
        query_filters["lease_end_date"] = ["between", [filters["from_date"], filters["to_date"]]]
    elif filters.get("from_date"):
        query_filters["lease_end_date"] = [">=", filters["from_date"]]
    elif filters.get("to_date"):
        query_filters["lease_end_date"] = ["<=", filters["to_date"]]

    leases = frappe.get_all(
        "Accommodation Lease",
        filters=query_filters,
        fields=["name", "building", "status", "lease_end_date", "rent_amount"],
        order_by="lease_end_date asc",
    )

    today_str = today()
    data = []
    for lease in leases:
        data.append({
            "name": lease["name"],
            "building": lease["building"],
            "status": lease["status"],
            "lease_end_date": lease["lease_end_date"],
            "days_to_expiry": (
                date_diff(lease["lease_end_date"], today_str) if lease.get("lease_end_date") else None
            ),
            "rent_amount": flt(lease.get("rent_amount")),
        })
    return columns, data
