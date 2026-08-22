# Copyright (c) 2026, afmcoltd

"""Safety Incident Register — what happened in each building, how serious it was, and
whether it is closed.

The rows are DOCUMENT rows: one incident is one record with its own severity, status
and casualty count, and there is no child line to unfold. Only submitted incidents are
listed — a draft has not been formally reported, and a cancelled incident is out with
docstatus 2.

Scoped by building through the same resolver the permission hook uses, so a scope
correction reaches this report and the desk list together.
"""

import frappe
from frappe import _

from apex.apex_core.utils.report_helpers import date_range_condition
from apex.apex_core.utils.report_summary import count_card, total_card
from apex.habitat import permissions

HIGH_SEVERITIES = ("High", "Severe", "Critical")


def execute(filters=None):
    """Returns the columns, rows and summary cards for submitted safety incidents in scope."""
    filters = filters or {}
    columns = get_columns()

    query_filters = {"docstatus": 1}
    for field in ("building", "incident_type", "severity", "status"):
        if filters.get(field):
            query_filters[field] = filters[field]
    date_condition = date_range_condition(filters, "incident_datetime")
    if date_condition is not None:
        query_filters["incident_datetime"] = date_condition

    restrict, allowed = permissions.report_building_scope(frappe.session.user, doctype="Safety Incident")
    if restrict:
        chosen = query_filters.get("building")
        if not allowed or (chosen and chosen not in allowed):
            return columns, [], None, None, get_report_summary([])
        if not chosen:
            query_filters["building"] = ["in", allowed]

    data = frappe.get_all(
        "Safety Incident",
        filters=query_filters,
        fields=[
            "name",
            "incident_datetime",
            "building",
            "specific_location",
            "incident_type",
            "severity",
            "status",
            "casualties",
            "reported_by",
        ],
        order_by="incident_datetime desc",
    )

    return columns, data, None, None, get_report_summary(data)


def get_report_summary(data):
    """Built for any result including none, so an empty register reads 0 rather than a
    blank strip that looks like a page which failed to load."""
    open_incidents = [r for r in data if r.get("status") != "Closed"]
    high = [r for r in data if r.get("severity") in HIGH_SEVERITIES]
    return [
        count_card(_("Incidents"), data),
        count_card(_("Open"), open_incidents, indicator="Orange" if open_incidents else None),
        count_card(_("High Severity"), high, indicator="Red" if high else None),
        total_card(_("Casualties"), data, "casualties", datatype="Int"),
    ]


def get_columns():
    """Returns the column definitions for the safety incident register."""
    return [
        {"label": _("Incident"), "fieldname": "name", "fieldtype": "Link", "options": "Safety Incident", "width": 160},
        {"label": _("Incident Date and Time"), "fieldname": "incident_datetime", "fieldtype": "Datetime", "width": 165},
        {"label": _("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 150},
        {"label": _("Specific Location"), "fieldname": "specific_location", "fieldtype": "Data", "width": 140},
        {"label": _("Incident Type"), "fieldname": "incident_type", "fieldtype": "Data", "width": 130},
        {"label": _("Severity"), "fieldname": "severity", "fieldtype": "Data", "width": 100},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
        {"label": _("Casualties"), "fieldname": "casualties", "fieldtype": "Int", "width": 95},
        {"label": _("Reported By"), "fieldname": "reported_by", "fieldtype": "Link", "options": "User", "width": 170},
    ]
