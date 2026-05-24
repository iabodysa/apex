# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, today


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": frappe._("Checkout"), "fieldname": "name", "fieldtype": "Link", "options": "Accommodation Checkout", "width": 150},
        {"label": frappe._("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 150},
        {"label": frappe._("Checkout Date"), "fieldname": "checkout_date", "fieldtype": "Date", "width": 120},
        {"label": frappe._("Custody Cleared"), "fieldname": "custody_cleared", "fieldtype": "Check", "width": 110},
        {"label": frappe._("Open Custody Issues"), "fieldname": "open_custody_issues", "fieldtype": "Int", "width": 130},
        {"label": frappe._("Damage Assessment"), "fieldname": "damage_assessment", "fieldtype": "Data", "width": 150},
        {"label": frappe._("Days Since Checkout"), "fieldname": "days_since", "fieldtype": "Int", "width": 130},
    ]

    query_filters = {"docstatus": 1}
    # Note: Accommodation Checkout has no "building" field — building is derived
    # per row via the bed link. The building filter is applied in the loop below.

    checkouts = frappe.get_all(
        "Accommodation Checkout",
        filters=query_filters,
        fields=["name", "employee", "bed", "checkout_date", "custody_cleared", "assignment"],
        order_by="checkout_date desc",
    )

    data = []
    for co in checkouts:
        # Count open custody issues for this employee
        open_issues = frappe.db.count(
            "Custody Issue",
            {"issued_to_employee": co.employee, "docstatus": 1},
        ) if co.employee else 0

        # Look for damage assessment linked to this checkout
        damage = frappe.db.get_value(
            "Custody Damage Assessment",
            {"employee": co.employee, "docstatus": 1},
            "name",
        ) or "" if co.employee else ""

        # Get building from bed
        building = frappe.db.get_value("Accommodation Bed", co.bed, "building") if co.bed else ""
        if filters.get("building") and building != filters.get("building"):
            continue

        days_since = (getdate(today()) - getdate(co.checkout_date)).days if co.checkout_date else 0

        # Show only if custody not cleared or damage exists or open issues
        if not co.custody_cleared or open_issues or damage:
            data.append({
                "name": co.name,
                "employee": co.employee,
                "building": building,
                "checkout_date": co.checkout_date,
                "custody_cleared": co.custody_cleared,
                "open_custody_issues": open_issues,
                "damage_assessment": damage,
                "days_since": days_since,
            })

    return columns, data
