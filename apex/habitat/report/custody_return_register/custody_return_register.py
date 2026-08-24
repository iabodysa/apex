# Copyright (c) 2026, afmcoltd


import frappe
from frappe import _

from apex.apex_core.utils.report_summary import count_card, percent_card
from apex.habitat import permissions

CHARGEABLE_CONDITIONS = ("Damaged", "Lost")


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()

    query_filters = {"docstatus": 1}
    for field in ("building", "returned_by_employee", "custody_issue"):
        if filters.get(field):
            query_filters[field] = filters[field]

    restrict, allowed = permissions.report_building_scope(frappe.session.user, doctype="Custody Return")
    if restrict:
        chosen = query_filters.get("building")
        if not allowed or (chosen and chosen not in allowed):
            return columns, [], None, None, get_report_summary([])
        if not chosen:
            query_filters["building"] = ["in", allowed]

    returns = frappe.get_all(
        "Custody Return",
        filters=query_filters,
        fields=[
            "name",
            "return_date",
            "building",
            "custody_issue",
            "returned_by_employee",
        ],
        order_by="return_date desc",
    )
    if not returns:
        return columns, [], None, None, get_report_summary([])

    lines = frappe.get_all(
        "Custody Return Item",
        filters={"parent": ["in", [r.name for r in returns]], "parenttype": "Custody Return"},
        fields=["parent", "article", "qty", "condition_on_return", "serial_no"],
        order_by="parent asc, idx asc",
    )
    by_name = {r.name: r for r in returns}

    data = []
    for line in lines:
        header = by_name.get(line.parent)
        if not header:
            continue
        condition = line.condition_on_return or ""
        data.append(
            {
                "name": line.parent,
                "return_date": header.return_date,
                "building": header.building,
                "custody_issue": header.custody_issue,
                "returned_by_employee": header.returned_by_employee,
                "article": line.article,
                "qty": line.qty,
                "condition_on_return": condition,
                "serial_no": line.serial_no,
                "is_chargeable": bool(condition in CHARGEABLE_CONDITIONS),
                "chargeable": _("Yes") if condition in CHARGEABLE_CONDITIONS else _("No"),
            }
        )

    if filters.get("chargeable_only"):
        data = [r for r in data if r.get("is_chargeable")]

    return columns, data, None, None, get_report_summary(data)


def get_report_summary(data):
    chargeable = [r for r in data if r.get("is_chargeable")]
    return [
        count_card(_("Returned Lines"), data),
        count_card(
            _("Returns"),
            [{"n": n} for n in {r.get("name") for r in data if r.get("name")}],
        ),
        count_card(
            _("Damaged or Lost"), chargeable, indicator="Red" if chargeable else None
        ),
        percent_card(_("Returned in Good Order"), len(data) - len(chargeable), len(data)),
    ]


def get_columns():
    return [
        {"label": _("Return"), "fieldname": "name", "fieldtype": "Link", "options": "Custody Return", "width": 170},
        {"label": _("Return Date"), "fieldname": "return_date", "fieldtype": "Date", "width": 110},
        {"label": _("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 150},
        {"label": _("Against Issue"), "fieldname": "custody_issue", "fieldtype": "Link", "options": "Custody Issue", "width": 170},
        {"label": _("Returned By"), "fieldname": "returned_by_employee", "fieldtype": "Link", "options": "Employee", "width": 150},
        {"label": _("Article"), "fieldname": "article", "fieldtype": "Link", "options": "Custody Article", "width": 160},
        {"label": _("Qty"), "fieldname": "qty", "fieldtype": "Int", "width": 80},
        {"label": _("Condition"), "fieldname": "condition_on_return", "fieldtype": "Data", "width": 110},
        {"label": _("Chargeable"), "fieldname": "chargeable", "fieldtype": "Data", "width": 110},
        {"label": _("Serial No"), "fieldname": "serial_no", "fieldtype": "Data", "width": 140},
    ]
