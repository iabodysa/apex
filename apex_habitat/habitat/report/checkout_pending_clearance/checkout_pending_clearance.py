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

    checkouts = frappe.get_all(
        "Accommodation Checkout",
        filters=query_filters,
        fields=["name", "employee", "bed", "checkout_date", "custody_cleared", "assignment"],
        order_by="checkout_date desc",
    )

    if not checkouts:
        return columns, []

    # --- Prefetch bed -> building mapping in one query ---
    all_beds = list({co.bed for co in checkouts if co.bed})
    bed_building_map = {}
    if all_beds:
        bed_rows = frappe.get_all(
            "Accommodation Bed",
            filters={"name": ["in", all_beds]},
            fields=["name", "building"],
        )
        bed_building_map = {b.name: b.building for b in bed_rows}

    # Apply building filter: keep only checkouts whose bed maps to the requested building
    building_filter = filters.get("building")
    if building_filter:
        checkouts = [
            co for co in checkouts
            if bed_building_map.get(co.bed) == building_filter
        ]

    if not checkouts:
        return columns, []

    all_employees = list({co.employee for co in checkouts if co.employee})

    # --- Prefetch open custody issue counts grouped by employee in one query ---
    issue_count_map = {}
    if all_employees:
        issue_rows = frappe.get_all(
            "Custody Issue",
            filters={"issued_to_employee": ["in", all_employees], "docstatus": 1},
            fields=["issued_to_employee", "count(name) as issue_count"],
            group_by="issued_to_employee",
        )
        issue_count_map = {r.issued_to_employee: r.issue_count for r in issue_rows}

    # --- Prefetch damage assessments grouped by employee (one per employee) ---
    damage_map = {}
    if all_employees:
        damage_rows = frappe.get_all(
            "Custody Damage Assessment",
            filters={"employee": ["in", all_employees], "docstatus": 1},
            fields=["employee", "name"],
            order_by="name asc",
        )
        # Keep first hit per employee (stable ordering)
        for dr in damage_rows:
            if dr.employee not in damage_map:
                damage_map[dr.employee] = dr.name

    today_date = getdate(today())
    data = []
    for co in checkouts:
        building = bed_building_map.get(co.bed, "") if co.bed else ""
        open_issues = issue_count_map.get(co.employee, 0) if co.employee else 0
        damage = damage_map.get(co.employee, "") if co.employee else ""
        days_since = (today_date - getdate(co.checkout_date)).days if co.checkout_date else 0

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
