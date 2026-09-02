# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _
from frappe.utils import flt

from apex.apex_core.utils.report_summary import count_card, total_card
from apex.habitat import permissions


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if not (from_date and to_date):
        frappe.throw(_("From Date and To Date are required."))

    scope = building_scope(filters)
    if scope is None:
        return columns, [], None, None, get_report_summary([])

    data = get_data(filters, ["between", [from_date, to_date]], scope)
    return columns, data, None, build_chart(data), get_report_summary(data)


def get_columns():
    return [
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": _("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 150},
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 150},
        {"label": _("Days Housed"), "fieldname": "days_housed", "fieldtype": "Int", "width": 110},
        {"label": _("Accommodation Cost"), "fieldname": "accommodation_cost", "fieldtype": "Currency", "width": 160},
        {"label": _("Custody Issued"), "fieldname": "custody_cost", "fieldtype": "Currency", "width": 140},
        {"label": _("Recovered from Employee"), "fieldname": "recovered", "fieldtype": "Currency", "width": 180},
        {"label": _("Net Cost"), "fieldname": "net_cost", "fieldtype": "Currency", "width": 140},
        {"label": _("Cost per Day"), "fieldname": "cost_per_day", "fieldtype": "Currency", "width": 130},
    ]


def building_scope(filters):
    chosen = filters.get("building")
    restrict, allowed = permissions.report_building_scope(
        frappe.session.user, doctype="Accommodation Ledger"
    )
    if restrict:
        if not allowed or (chosen and chosen not in allowed):
            return None
        return {"building": chosen} if chosen else {"building": ["in", allowed]}
    return {"building": chosen} if chosen else {}


def get_data(filters, window, scope):
    buckets = {}

    stay_filters = dict(scope, posting_mode="Operational Memo", posting_date=window)
    stay_filters["employee"] = ["is", "set"]
    for field in ("company", "project", "cost_center", "employee"):
        if filters.get(field):
            stay_filters[field] = filters[field]

    daily_net = {}
    for row in frappe.get_all(
        "Accommodation Ledger",
        filters=stay_filters,
        fields=["employee", "building", "project", "posting_date", "employee_daily_share"],
        order_by="posting_date asc",
    ):
        bucket = employee_bucket(buckets, row.employee)
        share = flt(row.employee_daily_share)
        bucket["accommodation_cost"] += share
        bucket["building"] = row.building or bucket["building"]
        bucket["project"] = row.project or bucket["project"]
        key = (row.employee, str(row.posting_date))
        daily_net[key] = daily_net.get(key, 0.0) + share

    for (employee, _posting_date), net in daily_net.items():
        if abs(net) > 1e-9:
            buckets[employee]["days_housed"] += 1

    custody_filters = dict(scope, posting_date=window, is_cancelled=0)
    custody_filters["employee"] = ["is", "set"]
    for field in ("company", "cost_center", "employee"):
        if filters.get(field):
            custody_filters[field] = filters[field]

    for row in frappe.get_all(
        "Accommodation Stock Ledger",
        filters=custody_filters,
        fields=["employee", "building", "signed_qty", "unit_cost"],
    ):
        bucket = employee_bucket(buckets, row.employee)
        bucket["custody_cost"] += flt(row.signed_qty) * flt(row.unit_cost)
        bucket["building"] = bucket["building"] or row.building or ""

    if not buckets:
        return []

    for employee, amount in recovered_by_employee(list(buckets), window, filters).items():
        buckets[employee]["recovered"] += amount

    names = {
        row.name: row.employee_name
        for row in frappe.get_all(
            "Employee",
            filters={"name": ["in", list(buckets)]},
            fields=["name", "employee_name"],
        )
    }

    data = []
    for employee, bucket in buckets.items():
        net = bucket["accommodation_cost"] + bucket["custody_cost"] - bucket["recovered"]
        days = bucket["days_housed"]
        data.append({
            "employee": employee,
            "employee_name": names.get(employee, ""),
            "building": bucket["building"],
            "project": bucket["project"],
            "days_housed": days,
            "accommodation_cost": flt(bucket["accommodation_cost"], 2),
            "custody_cost": flt(bucket["custody_cost"], 2),
            "recovered": flt(bucket["recovered"], 2),
            "net_cost": flt(net, 2),
            "cost_per_day": flt(net / days, 2) if days else 0.0,
        })

    data.sort(key=lambda row: row["net_cost"], reverse=True)
    return data


def employee_bucket(buckets, employee):
    return buckets.setdefault(employee, {
        "building": "",
        "project": "",
        "days_housed": 0,
        "accommodation_cost": 0.0,
        "custody_cost": 0.0,
        "recovered": 0.0,
    })


def recovered_by_employee(employees, window, filters):
    recovery_filters = {
        "docstatus": 1,
        "status": "Recovered",
        "request_date": window,
        "employee": ["in", employees],
    }
    for field in ("company", "cost_center"):
        if filters.get(field):
            recovery_filters[field] = filters[field]

    totals = {}
    for row in frappe.get_list(
        "Movement Cost Recovery",
        filters=recovery_filters,
        fields=["employee", "sum(amount) as amount"],
        group_by="employee",
    ):
        totals[row.employee] = flt(row.amount)
    return totals


def get_report_summary(data):
    return [
        count_card(_("Employees"), data),
        total_card(_("Accommodation Cost"), data, "accommodation_cost", "Currency"),
        total_card(_("Custody Issued"), data, "custody_cost", "Currency"),
        total_card(_("Net Cost"), data, "net_cost", "Currency"),
    ]


def build_chart(data):
    top = [row for row in data if row["net_cost"]][:10]
    if not top:
        return None
    return {
        "type": "bar",
        "data": {
            "labels": [row["employee_name"] or row["employee"] for row in top],
            "datasets": [{"name": _("Net Cost"), "values": [row["net_cost"] for row in top]}],
        },
    }
