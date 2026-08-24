# Copyright (c) 2026, afmcoltd


import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today

from apex.apex_core.utils.report_summary import count_card, percent_card
from apex.habitat import permissions

RETURNED_STATUSES = ("Returned",)


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()

    query_filters = {"docstatus": 1}
    for field in ("building", "status"):
        if filters.get(field):
            query_filters[field] = filters[field]
    if filters.get("issued_to_employee"):
        query_filters["issued_to_employee"] = filters["issued_to_employee"]

    restrict, allowed = permissions.report_building_scope(frappe.session.user, doctype="Custody Issue")
    if restrict:
        chosen = query_filters.get("building")
        if not allowed or (chosen and chosen not in allowed):
            return columns, [], None, None, get_report_summary([])
        if not chosen:
            query_filters["building"] = ["in", allowed]

    rows = frappe.get_all(
        "Custody Issue",
        filters=query_filters,
        fields=[
            "name",
            "issue_date",
            "building",
            "issued_to_employee",
            "issued_to_name",
            "expected_return_date",
            "acknowledged_on",
            "status",
        ],
        order_by="issue_date desc",
    )

    today_date = getdate(today())
    data = []
    for row in rows:
        outstanding = row.status not in RETURNED_STATUSES
        due = getdate(row.expected_return_date) if row.expected_return_date else None
        overdue = bool(outstanding and due and due < today_date)
        data.append(
            {
                **row,
                "is_acknowledged": bool(row.acknowledged_on),
                "acknowledged": _("Yes") if row.acknowledged_on else _("No"),
                "days_overdue": date_diff(today_date, due) if overdue else 0,
            }
        )

    if filters.get("overdue_only"):
        data = [r for r in data if r["days_overdue"] > 0]

    return columns, data, None, None, get_report_summary(data)


def get_report_summary(data):
    unsigned = [r for r in data if not r.get("is_acknowledged")]
    overdue = [r for r in data if r.get("days_overdue")]
    return [
        count_card(_("Issues"), data),
        count_card(_("Not Acknowledged"), unsigned, indicator="Red" if unsigned else None),
        count_card(_("Overdue"), overdue, indicator="Orange" if overdue else None),
        percent_card(_("Acknowledged"), len(data) - len(unsigned), len(data)),
    ]


def get_columns():
    return [
        {"label": _("Issue"), "fieldname": "name", "fieldtype": "Link", "options": "Custody Issue", "width": 170},
        {"label": _("Issue Date"), "fieldname": "issue_date", "fieldtype": "Date", "width": 110},
        {"label": _("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 160},
        {"label": _("Issued To"), "fieldname": "issued_to_employee", "fieldtype": "Link", "options": "Employee", "width": 150},
        {"label": _("Name"), "fieldname": "issued_to_name", "fieldtype": "Data", "width": 170},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
        {"label": _("Acknowledged"), "fieldname": "acknowledged", "fieldtype": "Data", "width": 120},
        {"label": _("Expected Return"), "fieldname": "expected_return_date", "fieldtype": "Date", "width": 130},
        {"label": _("Days Overdue"), "fieldname": "days_overdue", "fieldtype": "Int", "width": 120},
    ]
