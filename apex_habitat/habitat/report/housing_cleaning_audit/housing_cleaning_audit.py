# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

"""Housing Cleaning Audit.

Query Report that lets managers view Cleaning Log records per building,
filterable by date range, building, and derived status. Shows cleaning date,
building, cleaner, derived status, supervisor approval, and whether photo
evidence was attached (evidence_photo field).

Status is derived from the missed_cleaning and rework_required flags because
Cleaning Log has no dedicated status field:
  - Missed + Rework  : missed_cleaning=1 AND rework_required=1
  - Missed           : missed_cleaning=1 AND rework_required=0
  - Rework Required  : missed_cleaning=0 AND rework_required=1
  - Completed        : missed_cleaning=0 AND rework_required=0
"""

import frappe
from frappe.utils import getdate, today, add_days

from apex_habitat.habitat import permissions


def execute(filters=None):
    filters = filters or {}

    date_from = getdate(filters.get("from_date") or add_days(today(), -30))
    date_to = getdate(filters.get("to_date") or today())

    columns = [
        {
            "label": frappe._("Log"),
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Cleaning Log",
            "width": 140,
        },
        {
            "label": frappe._("Cleaning Date"),
            "fieldname": "cleaning_date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "label": frappe._("Building"),
            "fieldname": "building",
            "fieldtype": "Link",
            "options": "Accommodation Building",
            "width": 160,
        },
        {
            "label": frappe._("Cleaner Type"),
            "fieldname": "cleaner_type",
            "fieldtype": "Data",
            "width": 110,
        },
        {
            "label": frappe._("Cleaner"),
            "fieldname": "cleaner",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": frappe._("Status"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "label": frappe._("Supervisor Approved"),
            "fieldname": "supervisor_approved",
            "fieldtype": "Check",
            "width": 130,
        },
        {
            "label": frappe._("Photo Attached"),
            "fieldname": "has_photo",
            "fieldtype": "Data",
            "width": 100,
        },
    ]

    # Resolve building-level row scope (Housing Supervisor permission).
    # get_all bypasses permission_query_conditions, so we re-apply it manually.
    restrict, allowed = permissions.report_building_scope(frappe.session.user)
    chosen_building = filters.get("building")
    if restrict:
        if not allowed or (chosen_building and chosen_building not in allowed):
            return columns, []

    # Build parameterized SQL. Using frappe.db.sql with %s placeholders keeps
    # the query safe against injection while allowing flexible WHERE construction.
    conditions = ["cl.cleaning_date BETWEEN %(date_from)s AND %(date_to)s"]
    params = {
        "date_from": str(date_from),
        "date_to": str(date_to),
    }

    if chosen_building:
        conditions.append("cl.building = %(building)s")
        params["building"] = chosen_building
    elif restrict and allowed:
        # IN clause: frappe.db.sql does not natively expand lists; build inline.
        placeholders = ", ".join(f"%(bld_{i})s" for i, _ in enumerate(allowed))
        conditions.append(f"cl.building IN ({placeholders})")
        for i, bld in enumerate(allowed):
            params[f"bld_{i}"] = bld

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT
            cl.name,
            cl.cleaning_date,
            cl.building,
            cl.cleaner_type,
            cl.cleaner_employee,
            cl.cleaned_by,
            cl.missed_cleaning,
            cl.rework_required,
            cl.supervisor_approved,
            CASE
                WHEN cl.evidence_photo IS NOT NULL AND cl.evidence_photo != ''
                THEN 'Yes'
                ELSE 'No'
            END AS has_photo
        FROM `tabCleaning Log` cl
        WHERE {where_clause}
        ORDER BY cl.cleaning_date DESC, cl.building ASC
    """

    rows = frappe.db.sql(sql, params, as_dict=True)

    if not rows:
        return columns, []

    # Resolve employee names for internal cleaners.
    employee_ids = list({r.cleaner_employee for r in rows if r.get("cleaner_employee")})
    employee_name_map = {}
    if employee_ids:
        emp_rows = frappe.get_all(
            "Employee",
            filters={"name": ["in", employee_ids]},
            fields=["name", "employee_name"],
        )
        employee_name_map = {e.name: e.employee_name for e in emp_rows}

    # Derive status from flags.
    def _derive_status(missed, rework):
        if missed and rework:
            return "Missed + Rework"
        if missed:
            return "Missed"
        if rework:
            return "Rework Required"
        return "Completed"

    # Apply optional status filter after derivation (can't do this in SQL cleanly
    # because status is computed, not stored).
    status_filter = filters.get("status") or ""

    data = []
    for row in rows:
        cleaner_label = row.get("cleaned_by") or ""
        if row.get("cleaner_employee"):
            cleaner_label = employee_name_map.get(row.cleaner_employee) or row.cleaner_employee

        derived_status = _derive_status(
            bool(row.get("missed_cleaning")),
            bool(row.get("rework_required")),
        )

        if status_filter and derived_status != status_filter:
            continue

        data.append(
            {
                "name": row.name,
                "cleaning_date": row.cleaning_date,
                "building": row.building,
                "cleaner_type": row.cleaner_type or "",
                "cleaner": cleaner_label,
                "status": derived_status,
                "supervisor_approved": row.supervisor_approved,
                "has_photo": row.has_photo,
            }
        )

    return columns, data
