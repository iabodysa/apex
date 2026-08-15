# Copyright (c) 2026, afmcoltd

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from apex.habitat import permissions
from apex.apex_core.utils.report_summary import count_card, percent_card, total_card


def execute(filters=None):
    """Returns the per-building operations summary rows and summary cards for the selected date range."""
    filters = filters or {}

    date_from = getdate(filters.get("period_from") or add_days(today(), -7))
    date_to = getdate(filters.get("period_to") or today())
    building_filter = filters.get("building")

    columns = _columns()
    buildings = _get_buildings(building_filter)
    if not buildings:
        if _is_scope_gap(building_filter):
            return columns, [], _no_scope_message()
        return columns, []

    building_names = [b.name for b in buildings]

    occupancy = _occupancy(building_names)
    cleaning = _cleaning(building_names, date_from, date_to)
    safety = _safety_inspections(building_names, date_from, date_to)
    maintenance = _maintenance(building_names)
    resident = _resident_requests(building_names)

    data = []
    for b in buildings:
        n = b.name
        total = occupancy[n]["total"]
        occ = occupancy[n]["occupied"]
        occ_pct = round(occ / total * 100, 1) if total else 0.0

        cl = cleaning[n]
        compliance = round(cl["compliant"] / cl["total"] * 100, 1) if cl["total"] else 0.0

        data.append({
            "building": n,
            "total_beds": total,
            "occupied_beds": occ,
            "occupancy_pct": occ_pct,
            "cleaning_logs": cl["total"],
            "cleaning_compliance_pct": compliance,
            "missed_cleaning_logs": cl["missed"],
            "safety_inspections": safety[n],
            "open_maintenance": maintenance[n]["open"],
            "closed_maintenance": maintenance[n]["closed"],
            "open_resident_requests": resident[n],
        })

    summary = [
        count_card(_("Buildings"), data),
        total_card(_("Occupied Beds"), data, "occupied_beds", "Int"),
        percent_card(
            _("Occupancy"),
            sum(flt(r.get("occupied_beds")) for r in data),
            sum(flt(r.get("total_beds")) for r in data),
        ),
        total_card(_("Cleaning Logs"), data, "cleaning_logs", "Int"),
    ]
    return columns, data, None, None, summary


def _columns():
    """Returns the column definitions for the building operations summary report."""
    return [
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link",
         "options": "Building", "width": 180},
        {"label": frappe._("Total Beds"), "fieldname": "total_beds", "fieldtype": "Int", "width": 90},
        {"label": frappe._("Occupied Beds"), "fieldname": "occupied_beds", "fieldtype": "Int", "width": 110},
        {"label": frappe._("Occupancy %"), "fieldname": "occupancy_pct", "fieldtype": "Float",
         "precision": 1, "width": 100},
        {"label": frappe._("Cleaning Logs"), "fieldname": "cleaning_logs", "fieldtype": "Int", "width": 100},
        {"label": frappe._("Cleaning Compliance %"), "fieldname": "cleaning_compliance_pct",
         "fieldtype": "Float", "precision": 1, "width": 150},
        {"label": frappe._("Missed Cleaning Logs"), "fieldname": "missed_cleaning_logs",
         "fieldtype": "Int", "width": 130},
        {"label": frappe._("Safety Inspections"), "fieldname": "safety_inspections",
         "fieldtype": "Int", "width": 130},
        {"label": frappe._("Open Maintenance"), "fieldname": "open_maintenance",
         "fieldtype": "Int", "width": 130},
        {"label": frappe._("Closed Maintenance"), "fieldname": "closed_maintenance",
         "fieldtype": "Int", "width": 140},
        {"label": frappe._("Open Resident Requests"), "fieldname": "open_resident_requests",
         "fieldtype": "Int", "width": 160},
    ]


def _get_buildings(building_filter):
    """Returns active buildings restricted to the user's permitted buildings and any building filter."""
    f = {"status": "Active"}

    restrict, allowed = permissions.report_building_scope(frappe.session.user, doctype="Building")
    if restrict:
        if building_filter:
            allowed = [b for b in allowed if b == building_filter]
        if not allowed:
            return []
        f["name"] = ["in", allowed]
    elif building_filter:
        f["name"] = building_filter

    return frappe.get_all("Building", filters=f, fields=["name"], order_by="name")


def _is_scope_gap(building_filter):
    """True when an empty result is a building-scope gap (a scoped user with no
    User-Permission buildings) rather than a genuinely empty estate.

    An explicit out-of-scope ``building_filter`` is treated as a normal empty
    filter, not a scope gap.

    Reads the SAME narrowed scope ``_get_buildings`` reads. Reading the raw resolver
    here instead would leave a user whose only Building permission is ``applicable_for``
    some OTHER doctype with an empty report and no message explaining it.
    """
    restrict, allowed = permissions.report_building_scope(frappe.session.user, doctype="Building")
    if not restrict:
        return False
    if building_filter:
        return False
    return not allowed


def _no_scope_message():
    """Returns the message shown when a scoped user has no building permission at all."""
    return frappe._(
        "No active buildings are in your scope. Ask an Accommodation Manager to grant you"
        " a building permission, then reopen this report."
    )


def _occupancy(building_names):
    """Returns each building's total and occupied bed counts."""
    result = defaultdict(lambda: {"total": 0, "occupied": 0})

    beds = frappe.get_all("Bed", filters={"building": ["in", building_names]},
                           fields=["building", "status"])
    for bed in beds:
        result[bed.building]["total"] += 1
        if bed.status == "Occupied":
            result[bed.building]["occupied"] += 1

    return result


def _cleaning(building_names, date_from, date_to):
    """Returns each building's cleaning log totals, split into compliant and missed, for the window."""
    result = defaultdict(lambda: {"total": 0, "compliant": 0, "missed": 0})

    logs = frappe.get_all(
        "Cleaning Log",
        filters={"building": ["in", building_names],
                 "cleaning_date": ["between", [str(date_from), str(date_to)]]},
        fields=["building", "missed_cleaning"],
    )
    for log in logs:
        b = log.building
        result[b]["total"] += 1
        if log.missed_cleaning:
            result[b]["missed"] += 1
        else:
            result[b]["compliant"] += 1

    return result


def _safety_inspections(building_names, date_from, date_to):
    """Submitted safety checks per building in the window, across BOTH records.

    Safety Round is the live one. Safety Inspection Report is deprecated and
    nothing produces a new one, but it is still counted: it is the only record
    that exists for a period before the cutover, and reading only Safety Round
    would silently drop those periods to zero -- a report that empties reads as
    "the buildings were never checked", which is the opposite of the truth.
    The legacy leg becomes naturally dead as its window ages out; it is a read of
    history, not a write, so it does not keep the deprecated record alive.

    Each record carries its own date field (round_date / inspection_date), so the
    window is applied per leg rather than once.
    """
    result = defaultdict(int)
    window = ["between", [str(date_from), str(date_to)]]
    for doctype, date_field in (("Safety Round", "round_date"),
                                ("Safety Inspection Report", "inspection_date")):
        rows = frappe.get_all(
            doctype,
            filters={"building": ["in", building_names], "docstatus": 1,
                     date_field: window},
            fields=["building"],
        )
        for r in rows:
            result[r.building] += 1
    return result


def _maintenance(building_names):
    """Open and closed Maintenance Request counts per building.

    Native Frappe assignments own assignee state. Request lifecycle remains
    Open/In Progress/Resolved/Closed.
    """
    result = defaultdict(lambda: {"open": 0, "closed": 0})
    rows = frappe.get_all(
        "Maintenance Request",
        filters={"building": ["in", building_names], "docstatus": 1},
        fields=["building", "status"],
    )
    for r in rows:
        if r.status in ("Open", "In Progress", "Resolved"):
            result[r.building]["open"] += 1
        elif r.status == "Closed":
            result[r.building]["closed"] += 1
    return result


def _resident_requests(building_names):
    """Returns each building's count of open or triaged requests, mapped through QR location tokens."""
    result = defaultdict(int)
    tokens = frappe.get_all(
        "QR Location",
        filters={"building": ["in", building_names]},
        fields=["name", "building"],
    )
    token_to_building = {t.name: t.building for t in tokens}
    if not token_to_building:
        return result

    requests = frappe.get_all(
        "Resident Request",
        filters={"location_token": ["in", list(token_to_building.keys())],
                 "status": ["in", ["Open", "Triaged"]]},
        fields=["location_token"],
    )
    for r in requests:
        building = token_to_building.get(r.location_token)
        if building:
            result[building] += 1
    return result
