# Copyright (c) 2026, afmcoltd

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
best-effort from the live log.

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
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import add_days, getdate, today
from pypika import Order

from apex.apex_core.utils.report_summary import count_card, percent_card
from apex.habitat import permissions


def execute(filters=None):
    """Returns the rows and summary cards for the audit, with synthetic rows for missed building-days."""
    filters = filters or {}

    date_from = getdate(filters.get("from_date") or today())
    date_to = getdate(filters.get("to_date") or today())
    if date_to < date_from:
        date_to = date_from

    columns = get_columns()

    restrict, allowed = permissions.report_building_scope(frappe.session.user, doctype="Cleaning Log")
    chosen_building = filters.get("building") or ""
    if restrict:
        if not allowed or (chosen_building and chosen_building not in allowed):
            return columns, []

    bld_filters = {"status": "Active"}
    if chosen_building:
        bld_filters["name"] = chosen_building
    elif restrict and allowed:
        bld_filters["name"] = ["in", allowed]

    all_buildings = frappe.get_all(
        "Building",
        filters=bld_filters,
        fields=["name", "responsible_supervisor"],
    )
    if not all_buildings:
        return columns, []

    building_supervisor = _supervisor_by_building(all_buildings)

    rows = _cleaning_logs(date_from, date_to, chosen_building, allowed if restrict else None)
    rooms_cleaned_map, photos_map = _log_counts([r.name for r in rows])

    data = _logged_rows(rows, building_supervisor, rooms_cleaned_map, photos_map)
    covered = {(r["building"], str(r["cleaning_date"])) for r in data}
    data += _missed_rows(date_from, date_to, building_supervisor, covered)

    data.sort(key=lambda r: (str(r["cleaning_date"] or ""), r["building"] or ""),
              reverse=False)
    data.sort(key=lambda r: str(r["cleaning_date"] or ""), reverse=True)

    return columns, data, None, None, get_report_summary(data)


def _supervisor_by_building(all_buildings):
    """Maps each building to its supervisor's full name, falling back to the user id."""
    supervisor_ids = list({b.responsible_supervisor for b in all_buildings
                           if b.responsible_supervisor})
    supervisor_names: dict[str, str] = {}
    if supervisor_ids:
        for u in frappe.get_all(
            "User",
            filters={"name": ["in", supervisor_ids]},
            fields=["name", "full_name"],
        ):
            supervisor_names[u.name] = u.full_name or u.name

    return {
        b.name: supervisor_names.get(b.responsible_supervisor, b.responsible_supervisor or "")
        for b in all_buildings
    }


def _cleaning_logs(date_from, date_to, chosen_building, allowed):
    """Reads the non-cancelled Cleaning Logs in the window, newest day first."""
    cl = frappe.qb.DocType("Cleaning Log")
    query = (
        frappe.qb.from_(cl)
        .select(
            cl.name,
            cl.cleaning_date,
            cl.building,
            cl.missed_cleaning,
            cl.rework_required,
            cl.supervisor_approved,
            cl.docstatus,
            cl.modified,
        )
        .where(cl.cleaning_date.between(str(date_from), str(date_to)))
        .where(cl.docstatus != 2)
        .orderby(cl.cleaning_date, order=Order.desc)
        .orderby(cl.building, order=Order.asc)
    )
    if chosen_building:
        query = query.where(cl.building == chosen_building)
    elif allowed:
        query = query.where(cl.building.isin(allowed))

    return query.run(as_dict=True)


def _log_counts(log_names):
    """Returns (rooms cleaned, photos attached) per log, both keyed by Cleaning Log name."""
    rooms_cleaned_map: dict[str, int] = {}
    photos_map: dict[str, int] = {}
    if not log_names:
        return rooms_cleaned_map, photos_map

    for rec in frappe.get_all(
        "Cleaning Compliance Ledger",
        filters={"cleaning_log": ["in", log_names], "cleaned": 1, "is_cancelled": 0},
        fields=["cleaning_log", "count(name) as cnt"],
        group_by="cleaning_log",
    ):
        rooms_cleaned_map[rec.cleaning_log] = int(rec.cnt or 0)

    cap = frappe.qb.DocType("Cleaning Area Photo")
    for rec in (
        frappe.qb.from_(cap)
        .select(cap.parent, Count(cap.name).as_("cnt"))
        .where(cap.parent.isin(log_names))
        .groupby(cap.parent)
    ).run(as_dict=True):
        photos_map[rec.parent] = int(rec.cnt or 0)

    return rooms_cleaned_map, photos_map


def _derive_status(row) -> str:
    """Derives a log's status as Missed, Rework Required, Completed, or Pending from its flags."""
    if row.missed_cleaning:
        return "Missed"
    if row.rework_required:
        return "Rework Required"
    if row.supervisor_approved:
        return "Completed"
    return "Pending"


def _logged_rows(rows, building_supervisor, rooms_cleaned_map, photos_map):
    """Turns each Cleaning Log into a report row."""
    data = []
    for row in rows:
        building = row.building or ""
        data.append({
            "cleaning_date": row.cleaning_date,
            "building": building,
            "housing_supervisor": building_supervisor.get(building, ""),
            "status": _derive_status(row),
            "submitted_at": row.modified.date() if (row.docstatus == 1 and row.modified) else None,
            "rooms_cleaned": rooms_cleaned_map.get(row.name, 0),
            "photos_attached": photos_map.get(row.name, 0),
        })
    return data


def _missed_rows(date_from, date_to, building_supervisor, covered):
    """Builds a synthetic Missed row for every building-day the logs never covered."""
    data = []
    current = date_from
    while current <= date_to:
        date_str = str(current)
        for bld_name in sorted(building_supervisor):
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
    return data


def get_report_summary(data):
    """Builds the four summary cards; the labels stay inside _() so the language is per call."""
    missed_count = len([r for r in data if r.get("status") == "Missed"])
    return [
        count_card(_("Cleaning Days"), data),
        count_card(_("Missed"), data, lambda r: r.get("status") == "Missed", "Red"),
        count_card(
            _("Rework Required"),
            data,
            lambda r: r.get("status") == "Rework Required",
            "Orange",
        ),
        percent_card(_("Compliance"), len(data) - missed_count, len(data)),
    ]


def get_columns():
    """Returns the column definitions for the housing cleaning audit report."""
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
