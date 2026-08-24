# Copyright (c) 2026, afmcoltd


import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today

from apex.apex_core.utils.report_summary import count_card, percent_card
from apex.salis import permissions

LIVE_STATUS = "Active"


def execute(filters=None):
    filters = filters or {}
    columns = get_columns(filters)

    query_filters = {"docstatus": 1}
    if not filters.get("include_ended"):
        query_filters["status"] = LIVE_STATUS
        query_filters["end_date"] = ["is", "not set"]
    for field in ("vehicle", "driver", "project"):
        if filters.get(field):
            query_filters[field] = filters[field]

    restrict, allowed = permissions.report_project_scope(frappe.session.user, doctype="Vehicle Assignment")
    if restrict:
        chosen = query_filters.get("project")
        if not allowed or (chosen and chosen not in allowed):
            return columns, [], None, None, get_report_summary([])
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
                "is_held": bool(live),
                "held": _("Yes") if live else _("No"),
                "days_held": date_diff(until, start) if start else 0,
            }
        )

    return columns, data, None, None, get_report_summary(data)


def get_report_summary(data):
    live = [r for r in data if r.get("is_held")]
    return [
        count_card(_("Assignments"), data),
        count_card(_("Currently Held"), live, indicator="Green"),
        count_card(
            _("Vehicles"), [{"v": v} for v in {r.get("vehicle") for r in data if r.get("vehicle")}]
        ),
        percent_card(_("Still Held"), len(live), len(data)),
    ]


def get_columns(filters):
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
