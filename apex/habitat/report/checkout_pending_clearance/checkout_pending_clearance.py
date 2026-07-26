# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

"""Checkout Pending Clearance — Script Report.

Row scope (A-225). Every query below is ``frappe.get_all``, which forces the
ignore-permissions path, so the ``Housing Checkout`` row boundary registered in
``hooks.permission_query_conditions`` never reaches this SQL — a Script Report inherits
nothing from it. ``Resident Supervisor`` is in the report's audience and is NOT in
``habitat.permissions.HOUSING_UNSCOPED_ROLES``, so the scope has to be re-applied here in
Python or that role reads every estate.

Two boundaries, deliberately separate. ``readable`` is the permission boundary and gates
the joined custody rows; ``listed`` is ``readable`` narrowed by the user's own building
filter and gates the checkout list. Keeping them apart means an oversight role picking a
building still gets that employee's full custody counts, while a scoped supervisor's
counts and damage-assessment names stay confined to buildings they hold — the count and
the name were the actual disclosure, not just the checkout row.
"""

import frappe
from frappe.utils import date_diff, today

from apex.habitat import permissions


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": frappe._("Checkout"), "fieldname": "name", "fieldtype": "Link", "options": "Housing Checkout", "width": 150},
        {"label": frappe._("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150},
        {"label": frappe._("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 150},
        {"label": frappe._("Checkout Date"), "fieldname": "checkout_date", "fieldtype": "Date", "width": 120},
        {"label": frappe._("Custody Cleared"), "fieldname": "custody_cleared", "fieldtype": "Check", "width": 110},
        {"label": frappe._("Open Custody Issues"), "fieldname": "open_custody_issues", "fieldtype": "Int", "width": 130},
        {"label": frappe._("Damage Assessment"), "fieldname": "damage_assessment", "fieldtype": "Data", "width": 150},
        {"label": frappe._("Days Since Checkout"), "fieldname": "days_since", "fieldtype": "Int", "width": 130},
    ]

    restrict, allowed = permissions.report_building_scope(frappe.session.user)
    chosen_building = filters.get("building") or ""
    if restrict and (not allowed or (chosen_building and chosen_building not in allowed)):
        return columns, []

    readable = list(allowed) if restrict else []
    listed = [chosen_building] if chosen_building else readable

    query_filters = {"docstatus": 1}
    if listed:
        # Housing Checkout has no building column, so narrow it by its in-scope beds.
        in_scope_beds = frappe.get_all(
            "Bed", filters={"building": ["in", listed]}, pluck="name"
        )
        if not in_scope_beds:
            return columns, []
        query_filters["bed"] = ["in", in_scope_beds]

    checkouts = frappe.get_all(
        "Housing Checkout",
        filters=query_filters,
        fields=["name", "employee", "bed", "checkout_date", "custody_cleared"],
        order_by="checkout_date desc",
    )

    if not checkouts:
        return columns, []

    # [#c1vjzi]
    all_beds = list({co.bed for co in checkouts if co.bed})
    bed_building_map = {}
    if all_beds:
        bed_rows = frappe.get_all(
            "Bed",
            filters={"name": ["in", all_beds]},
            fields=["name", "building"],
        )
        bed_building_map = {b.name: b.building for b in bed_rows}

    all_employees = list({co.employee for co in checkouts if co.employee})

    # [#3wwr48]
    emp_name_map = {}
    if all_employees:
        emp_name_map = {
            e.name: e.employee_name
            for e in frappe.get_all(
                "Employee",
                filters={"name": ["in", all_employees]},
                fields=["name", "employee_name"],
            )
        }

    # [#7kb61x]
    issue_count_map = {}
    if all_employees:
        issue_filters = {"issued_to_employee": ["in", all_employees], "docstatus": 1}
        if readable:
            issue_filters["building"] = ["in", readable]
        issue_rows = frappe.get_all(
            "Custody Issue",
            filters=issue_filters,
            fields=["issued_to_employee", "count(name) as issue_count"],
            group_by="issued_to_employee",
        )
        issue_count_map = {r.issued_to_employee: r.issue_count for r in issue_rows}

    # [#5jlugb]
    damage_map = {}
    if all_employees:
        damage_filters = {"employee": ["in", all_employees], "docstatus": 1}
        if readable:
            damage_filters["building"] = ["in", readable]
        damage_rows = frappe.get_all(
            "Custody Damage Assessment",
            filters=damage_filters,
            fields=["employee", "name"],
            order_by="name asc",
        )
        # [#5kjdyq]
        for dr in damage_rows:
            if dr.employee not in damage_map:
                damage_map[dr.employee] = dr.name

    today_str = today()
    data = []
    for co in checkouts:
        building = bed_building_map.get(co.bed, "") if co.bed else ""
        open_issues = issue_count_map.get(co.employee, 0) if co.employee else 0
        damage = damage_map.get(co.employee, "") if co.employee else ""
        days_since = date_diff(today_str, co.checkout_date) if co.checkout_date else 0

        # [#nlghie]
        if not co.custody_cleared or open_issues or damage:
            data.append({
                "name": co.name,
                "employee": co.employee,
                "employee_name": emp_name_map.get(co.employee, "") if co.employee else "",
                "building": building,
                "checkout_date": co.checkout_date,
                "custody_cleared": co.custody_cleared,
                "open_custody_issues": open_issues,
                "damage_assessment": damage,
                "days_since": days_since,
            })

    return columns, data
