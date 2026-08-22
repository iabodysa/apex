# Copyright (c) 2026, afmcoltd

"""Resident Request Register — the open queue, and how long it has been waiting.

Resident Request had no report at all. A coordinator could only see the queue as a list
view, which shows rows but never the two things that decide what to do next: how long a
request has been sitting, and which of them nobody has taken.

An OPEN request is one whose status is not a settled one. The settled set is named here
rather than inferred from `closed_on`, because a Rejected request is settled without ever
being closed, and reading the date alone would leave it in the queue forever.

UNASSIGNED is its own figure and not a status: a request can be Triaged, In Progress or
Waiting Evidence and still carry no `assigned_to`, which is the state where a queue quietly
stops moving because everyone assumes someone else has it.

Scoped by building through the same resolver the permission hook uses, so a scope
correction reaches this report and the desk list together.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today

from apex.apex_core.utils.report_summary import count_card, percent_card
from apex.habitat import permissions

SETTLED_STATUSES = ("Resolved", "Rejected", "Closed")
URGENT_PRIORITIES = ("High", "Critical")
AGEING_DAYS = 7


def execute(filters=None):
    """Returns the columns, rows and summary cards for the open resident request queue and wait times."""
    filters = filters or {}
    columns = get_columns()

    query_filters = {}
    for field in ("building", "status", "priority", "assigned_to"):
        if filters.get(field):
            query_filters[field] = filters[field]
    if not filters.get("include_settled") and not filters.get("status"):
        query_filters["status"] = ["not in", list(SETTLED_STATUSES)]

    restrict, allowed = permissions.report_building_scope(frappe.session.user, doctype="Resident Request")
    if restrict:
        chosen = query_filters.get("building")
        if not allowed or (chosen and chosen not in allowed):
            return columns, [], None, None, get_report_summary([])
        if not chosen:
            query_filters["building"] = ["in", allowed]

    rows = frappe.get_all(
        "Resident Request",
        filters=query_filters,
        fields=[
            "name",
            "creation",
            "building",
            "room",
            "worker_name",
            "priority",
            "status",
            "assigned_to",
            "closed_on",
        ],
        order_by="creation asc",
    )

    today_date = getdate(today())
    data = []
    for row in rows:
        settled = row.status in SETTLED_STATUSES
        until = getdate(row.closed_on) if (settled and row.closed_on) else today_date
        data.append(
            {
                **row,
                "raised_on": getdate(row.creation),
                "days_waiting": date_diff(until, getdate(row.creation)),
                "is_owner_taken": bool(row.assigned_to),
                "owner_taken": _("Yes") if row.assigned_to else _("No"),
            }
        )

    if filters.get("unassigned_only"):
        data = [r for r in data if not r.get("is_owner_taken")]

    return columns, data, None, None, get_report_summary(data)


def get_report_summary(data):
    """Built for any result including none, so an empty queue reads 0 rather than a blank
    strip that looks like a page which failed to load."""
    unassigned = [r for r in data if not r.get("is_owner_taken")]
    urgent = [r for r in data if r.get("priority") in URGENT_PRIORITIES]
    ageing = [r for r in data if (r.get("days_waiting") or 0) > AGEING_DAYS]
    return [
        count_card(_("Requests"), data),
        count_card(_("Unassigned"), unassigned, indicator="Red" if unassigned else None),
        count_card(_("High or Critical"), urgent, indicator="Orange" if urgent else None),
        percent_card(_("Waiting Over a Week"), len(ageing), len(data)),
    ]


def get_columns():
    """Returns the column definitions for the resident request register."""
    return [
        {"label": _("Request"), "fieldname": "name", "fieldtype": "Link", "options": "Resident Request", "width": 170},
        {"label": _("Raised On"), "fieldname": "raised_on", "fieldtype": "Date", "width": 110},
        {"label": _("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 160},
        {"label": _("Room"), "fieldname": "room", "fieldtype": "Link", "options": "Room", "width": 110},
        {"label": _("Worker"), "fieldname": "worker_name", "fieldtype": "Data", "width": 160},
        {"label": _("Priority"), "fieldname": "priority", "fieldtype": "Data", "width": 100},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
        {"label": _("Assigned To"), "fieldname": "assigned_to", "fieldtype": "Link", "options": "User", "width": 170},
        {"label": _("Taken"), "fieldname": "owner_taken", "fieldtype": "Data", "width": 90},
        {"label": _("Days Waiting"), "fieldname": "days_waiting", "fieldtype": "Int", "width": 120},
    ]
