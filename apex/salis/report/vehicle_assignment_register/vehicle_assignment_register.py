# Copyright (c) 2026, AFMCO and contributors

"""Vehicle Assignment Register — who holds which vehicle, and who held it before.

The question this answers is "who has vehicle X today", which nothing could answer from a
report: Vehicle Assignment had no register at all, so the only way to see a vehicle's
current holder was to open the vehicle and read a link, and the only way to see its
history was to filter a list view by hand.

An assignment is LIVE when it is submitted, its status is Active and it carries no end
date. A submitted row that someone ended keeps its Active status, so the end date is what
decides — reading the status alone would show a vehicle as held by a driver who returned
it. That rule is stated once here and used by both the rows and the summary.

Defaults to the live assignments only. Pass ``include_ended`` to see the history beside
them, and the register then also carries each row's duration in days.

Scoped: a user confined to projects sees only assignments on those projects. The scope
comes from the same resolver the permission hook uses, so a scope correction reaches this
report and the desk list together.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today

from apex.apex_core.utils.report_summary import count_card, percent_card
from apex.salis import permissions

LIVE_STATUS = "Active"


def execute(filters=None):
    filters = filters or {}
    columns = _columns(filters)

    query_filters = {"docstatus": 1}
    if not filters.get("include_ended"):
        query_filters["status"] = LIVE_STATUS
        query_filters["end_date"] = ["is", "not set"]
    for field in ("vehicle", "driver", "project"):
        if filters.get(field):
            query_filters[field] = filters[field]

    restrict, allowed = permissions.report_project_scope(frappe.session.user)
    if restrict:
        chosen = query_filters.get("project")
        if not allowed or (chosen and chosen not in allowed):
            return columns, [], None, None, _summary([])
        if not chosen:
            query_filters["project"] = ["in", allowed]

    rows = frappe.get_all(
        "Vehicle Assignment",
        filters=query_filters,
        fields=[
            "name",
            "vehicle",
            "driver",
            "project",
            "supervisor",
            "start_date",
            "end_date",
            "status",
        ],
        order_by="vehicle asc, start_date desc",
    )

    today_date = getdate(today())
    data = []
    for row in rows:
        live = row.status == LIVE_STATUS and not row.end_date
        start = getdate(row.start_date) if row.start_date else None
        until = getdate(row.end_date) if row.end_date else today_date
        data.append(
            {
                **row,
                "held": _("Yes") if live else _("No"),
                "days_held": date_diff(until, start) if start else 0,
            }
        )

    return columns, data, None, None, _summary(data)


def _summary(data):
    """Built for any result including none, so an empty register reads 0 rather than
    blank — a blank strip looks like a page that failed to load."""
    live = [r for r in data if r.get("held") == _("Yes")]
    return [
        count_card(_("Assignments"), data),
        count_card(_("Currently Held"), live, indicator="Green"),
        count_card(
            _("Vehicles"), [{"v": v} for v in {r.get("vehicle") for r in data if r.get("vehicle")}]
        ),
        percent_card(_("Still Held"), len(live), len(data)),
    ]


def _columns(filters):
    columns = [
        {"label": _("Assignment"), "fieldname": "name", "fieldtype": "Link", "options": "Vehicle Assignment", "width": 150},
        {"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 150},
        {"label": _("Driver"), "fieldname": "driver", "fieldtype": "Link", "options": "Salis Driver", "width": 170},
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
        {"label": _("Supervisor"), "fieldname": "supervisor", "fieldtype": "Link", "options": "User", "width": 170},
        {"label": _("Start Date"), "fieldname": "start_date", "fieldtype": "Date", "width": 110},
        {"label": _("Currently Held"), "fieldname": "held", "fieldtype": "Data", "width": 120},
    ]
    if filters.get("include_ended"):
        columns += [
            {"label": _("End Date"), "fieldname": "end_date", "fieldtype": "Date", "width": 110},
            {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
            {"label": _("Days Held"), "fieldname": "days_held", "fieldtype": "Int", "width": 100},
        ]
    return columns
