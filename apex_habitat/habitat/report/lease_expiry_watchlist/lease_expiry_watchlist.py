# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import date_diff, today


def execute(filters=None):
    columns = [
        {"label": frappe._("Lease"), "fieldname": "name", "fieldtype": "Link", "options": "Accommodation Lease", "width": 150},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 160},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": frappe._("Lease End Date"), "fieldname": "lease_end_date", "fieldtype": "Date", "width": 120},
        {"label": frappe._("Days to Expiry"), "fieldname": "days_to_expiry", "fieldtype": "Int", "width": 120},
        {"label": frappe._("Monthly Rent (SAR)"), "fieldname": "rent_amount", "fieldtype": "Currency", "width": 140},
    ]

    leases = frappe.get_all(
        "Accommodation Lease",
        filters={"docstatus": 1, "status": "Active"},
        fields=["name", "building", "status", "lease_end_date", "rent_amount"],
        order_by="lease_end_date asc",
    )

    today_str = today()
    data = []
    for lease in leases:
        lease["days_to_expiry"] = (
            date_diff(lease["lease_end_date"], today_str) if lease.get("lease_end_date") else None
        )
        data.append(lease)
    return columns, data
