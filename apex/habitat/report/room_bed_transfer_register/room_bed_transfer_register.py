# Copyright (c) 2026, afmcoltd

"""Room Bed Transfer Register — who moved, from which bed to which bed, and when.

The rows are DOCUMENT rows: one transfer moves one resident, so there is no child line
to unfold. Only submitted transfers are listed — a draft has not moved anyone, and a
cancelled transfer is out with docstatus 2.

The transfer carries no building of its own; its building is the one on the Housing
Assignment it amends, which is the same hop the permission map declares. Scoped by that
building through the same resolver the permission hook uses, so a scope correction
reaches this report and the desk list together.
"""

import frappe
from frappe import _

from apex.apex_core.utils.report_helpers import date_range_condition
from apex.apex_core.utils.report_summary import count_card
from apex.habitat import permissions


def execute(filters=None):
    """Returns submitted Room Bed Transfers with building, scoped by permission, with summary cards."""
    filters = filters or {}
    columns = _columns()

    query_filters = {"docstatus": 1}
    if filters.get("party_type"):
        query_filters["party_type"] = filters["party_type"]
    date_condition = date_range_condition(filters, "transfer_date")
    if date_condition is not None:
        query_filters["transfer_date"] = date_condition

    chosen = filters.get("building")
    scope_buildings = [chosen] if chosen else None
    restrict, allowed = permissions.report_building_scope(frappe.session.user, doctype="Room Bed Transfer")
    if restrict:
        if not allowed or (chosen and chosen not in allowed):
            return columns, [], None, None, _summary([])
        if not chosen:
            scope_buildings = allowed
    if scope_buildings is not None:
        assignments = frappe.get_all("Housing Assignment", filters={"building": ["in", scope_buildings]}, pluck="name")
        if not assignments:
            return columns, [], None, None, _summary([])
        query_filters["assignment"] = ["in", assignments]

    rows = frappe.get_all(
        "Room Bed Transfer",
        filters=query_filters,
        fields=[
            "name",
            "transfer_date",
            "assignment",
            "party_type",
            "party",
            "from_bed",
            "to_room",
            "to_bed",
            "reason",
        ],
        order_by="transfer_date desc",
    )
    if not rows:
        return columns, [], None, None, _summary([])

    building_by_assignment = {
        a.name: a.building
        for a in frappe.get_all(
            "Housing Assignment",
            filters={"name": ["in", list({r.assignment for r in rows if r.assignment})]},
            fields=["name", "building"],
        )
    }

    data = [
        {**row, "building": building_by_assignment.get(row.assignment)} for row in rows
    ]

    return columns, data, None, None, _summary(data)


def _summary(data):
    """Built for any result including none, so an empty register reads 0 rather than a
    blank strip that looks like a page which failed to load."""
    residents = {r.get("party") for r in data if r.get("party")}
    employees = [r for r in data if r.get("party_type") == "Employee"]
    workers = [r for r in data if r.get("party_type") == "Temporary Worker"]
    return [
        count_card(_("Transfers"), data),
        count_card(_("Residents Moved"), [{"p": p} for p in residents]),
        count_card(_("Employee Transfers"), employees),
        count_card(_("Temporary Worker Transfers"), workers),
    ]


def _columns():
    """Returns the column definitions for the room bed transfer register."""
    return [
        {"label": _("Transfer"), "fieldname": "name", "fieldtype": "Link", "options": "Room Bed Transfer", "width": 160},
        {"label": _("Transfer Date"), "fieldname": "transfer_date", "fieldtype": "Date", "width": 115},
        {"label": _("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 150},
        {"label": _("Resident Type"), "fieldname": "party_type", "fieldtype": "Data", "width": 120},
        {"label": _("Resident"), "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 160},
        {"label": _("From Bed"), "fieldname": "from_bed", "fieldtype": "Link", "options": "Bed", "width": 140},
        {"label": _("To Room"), "fieldname": "to_room", "fieldtype": "Link", "options": "Room", "width": 140},
        {"label": _("To Bed"), "fieldname": "to_bed", "fieldtype": "Link", "options": "Bed", "width": 140},
        {"label": _("Reason"), "fieldname": "reason", "fieldtype": "Small Text", "width": 220},
    ]
