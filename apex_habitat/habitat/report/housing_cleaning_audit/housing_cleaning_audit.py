# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

"""Housing Cleaning Audit — Script Report.

Columns: date, building, housing_supervisor, status, submitted_at,
rooms_cleaned (the posted cleaned-room count), photos_attached
(count of area_photos child rows).

rooms_cleaned is the immutable posted fact: it is read from the Cleaning
Compliance Ledger (one live row per cleaned room, is_cancelled=0), NOT from the
mutable Cleaning Log Room Detail child rows. So a historical cleaned-room count
does not change when the source log's child rows are later edited; a cancel
posts a negating reversal (flagged is_cancelled) that nets the log out of the
live count. The status/supervisor/photos columns are review-state and stay
best-effort from the live log, mirroring daily_cleaning_compliance.

Gap detection: for every (date, building) combination in the requested
[from_date..to_date] window where no Cleaning Log exists (even a draft),
a synthetic "Missed" row is emitted so managers can see missing coverage at a
glance without needing to cross-reference the building list manually.

Status derivation (for logs that do exist):
  - Missed         : missed_cleaning=1
  - Rework Required: rework_required=1 (and not missed)
  - Completed      : supervisor_approved=1 (not missed/rework)
  - Pending        : draft (docstatus=0), none of the above flags set

Permission: Housing Supervisor users see only their own building(s).
"""

import frappe
from frappe.utils import add_days, getdate, today

from apex_habitat.habitat import permissions


def execute(filters=None):
    filters = filters or {}

    date_from = getdate(filters.get("from_date") or today())
    date_to = getdate(filters.get("to_date") or today())
    if date_to < date_from:
        date_to = date_from

    columns = _columns()

    # Building-level row scope for Housing Supervisor role.
    restrict, allowed = permissions.report_building_scope(frappe.session.user)
    chosen_building = filters.get("building") or ""
    if restrict:
        if not allowed or (chosen_building and chosen_building not in allowed):
            return columns, []

    # Determine which buildings to check (for gap detection).
    bld_filters = {"status": "Active"}
    if chosen_building:
        bld_filters["name"] = chosen_building
    elif restrict and allowed:
        bld_filters["name"] = ["in", allowed]

    all_buildings = frappe.get_all(
        "Building",
        filters=bld_filters,
        fields=["name", "responsible_facility_supervisor"],
    )
    if not all_buildings:
        return columns, []

    # Build supervisor display name map (one query, not N+1).
    supervisor_ids = list({b.responsible_facility_supervisor for b in all_buildings
                           if b.responsible_facility_supervisor})
    supervisor_names: dict[str, str] = {}
    if supervisor_ids:
        for u in frappe.get_all(
            "User",
            filters={"name": ["in", supervisor_ids]},
            fields=["name", "full_name"],
        ):
            supervisor_names[u.name] = u.full_name or u.name

    building_supervisor: dict[str, str] = {
        b.name: supervisor_names.get(b.responsible_facility_supervisor, b.responsible_facility_supervisor or "")
        for b in all_buildings
    }
    building_names_set = set(building_supervisor)

    # Fetch Cleaning Log rows in the date window.
    log_conditions = [
        "cl.cleaning_date BETWEEN %(date_from)s AND %(date_to)s",
        "cl.docstatus != 2",
    ]
    params: dict = {"date_from": str(date_from), "date_to": str(date_to)}

    if chosen_building:
        log_conditions.append("cl.building = %(building)s")
        params["building"] = chosen_building
    elif restrict and allowed:
        placeholders = ", ".join(f"%(bld_{i})s" for i, _ in enumerate(allowed))
        log_conditions.append(f"cl.building IN ({placeholders})")
        for i, bld in enumerate(allowed):
            params[f"bld_{i}"] = bld

    where = " AND ".join(log_conditions)
    sql = f"""
        SELECT
            cl.name,
            cl.cleaning_date,
            cl.building,
            cl.missed_cleaning,
            cl.rework_required,
            cl.supervisor_approved,
            cl.docstatus,
            cl.modified
        FROM `tabCleaning Log` cl
        WHERE {where}
        ORDER BY cl.cleaning_date DESC, cl.building ASC
    """
    rows = frappe.db.sql(sql, params, as_dict=True)

    # Pre-fetch room_details counts (cleaned=1) per Cleaning Log in one query.
    log_names = [r.name for r in rows]
    rooms_cleaned_map: dict[str, int] = {}
    photos_map: dict[str, int] = {}

    if log_names:
        # rooms_cleaned is the immutable posted fact: read the cleaned-room count
        # from the Cleaning Compliance Ledger (one live row per cleaned room), not
        # the mutable Cleaning Log Room Detail child rows, so the historical count
        # is stable. Only live rows (is_cancelled=0) count; a cancel posts a
        # negating reversal that nets the log out.
        for rec in frappe.get_all(
            "Cleaning Compliance Ledger",
            filters={"cleaning_log": ["in", log_names], "cleaned": 1, "is_cancelled": 0},
            fields=["cleaning_log", "count(name) as cnt"],
            group_by="cleaning_log",
        ):
            rooms_cleaned_map[rec.cleaning_log] = int(rec.cnt or 0)

        # Count area_photos rows per log (field: area_photos → child table
        # "Cleaning Area Photo" as confirmed from cleaning_log.json).
        for rec in frappe.db.sql(
            """
            SELECT parent, COUNT(*) AS cnt
            FROM `tabCleaning Area Photo`
            WHERE parent IN %(names)s
            GROUP BY parent
            """,
            {"names": log_names},
            as_dict=True,
        ):
            photos_map[rec.parent] = int(rec.cnt or 0)

    # Build a set of (building, date) pairs that have a log, for gap detection.
    covered: set[tuple[str, str]] = set()
    data = []

    def _derive_status(row) -> str:
        if row.missed_cleaning:
            return "Missed"
        if row.rework_required:
            return "Rework Required"
        if row.supervisor_approved:
            return "Completed"
        return "Pending"

    for row in rows:
        building = row.building or ""
        cleaning_date = row.cleaning_date
        covered.add((building, str(cleaning_date)))

        # submitted_at: use modified date when docstatus=1 (submitted).
        submitted_at = row.modified.date() if (row.docstatus == 1 and row.modified) else None

        data.append({
            "cleaning_date": cleaning_date,
            "building": building,
            "housing_supervisor": building_supervisor.get(building, ""),
            "status": _derive_status(row),
            "submitted_at": submitted_at,
            "rooms_cleaned": rooms_cleaned_map.get(row.name, 0),
            "photos_attached": photos_map.get(row.name, 0),
        })

    # Gap detection: emit a "Missed" synthetic row for every (building, date)
    # with no Cleaning Log at all in the requested window.
    current = date_from
    while current <= date_to:
        date_str = str(current)
        for bld_name in sorted(building_names_set):
            if (bld_name, date_str) not in covered:
                data.append({
                    "cleaning_date": current,
                    "building": bld_name,
                    "housing_supervisor": building_supervisor.get(bld_name, ""),
                    "status": "Missed",
                    "submitted_at": None,
                    "rooms_cleaned": 0,
                    "photos_attached": 0,
                })
        current = getdate(add_days(current, 1))

    # Sort: date descending, building ascending for a readable audit view.
    data.sort(key=lambda r: (str(r["cleaning_date"] or ""), r["building"] or ""),
              reverse=False)
    data.sort(key=lambda r: str(r["cleaning_date"] or ""), reverse=True)

    return columns, data


def _columns():
    return [
        {
            "label": frappe._("Date"),
            "fieldname": "cleaning_date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "label": frappe._("Building"),
            "fieldname": "building",
            "fieldtype": "Link",
            "options": "Building",
            "width": 160,
        },
        {
            "label": frappe._("Housing Supervisor"),
            "fieldname": "housing_supervisor",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": frappe._("Status"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": frappe._("Submitted At"),
            "fieldname": "submitted_at",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": frappe._("Rooms Cleaned"),
            "fieldname": "rooms_cleaned",
            "fieldtype": "Int",
            "width": 110,
        },
        {
            "label": frappe._("Photos Attached"),
            "fieldname": "photos_attached",
            "fieldtype": "Int",
            "width": 110,
        },
    ]
