# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _
from frappe.utils import flt

from apex.apex_core.utils.report_summary import count_card, total_card


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if not (from_date and to_date):
        frappe.throw(_("From Date and To Date are required."))

    drivers = in_scope_drivers(filters)
    if not drivers:
        return columns, [], None, None, get_report_summary([])

    data = get_data(drivers, ["between", [from_date, to_date]], filters)
    return columns, data, None, build_chart(data), get_report_summary(data)


def get_columns():
    return [
        {"label": _("Driver"), "fieldname": "driver", "fieldtype": "Link", "options": "Salis Driver", "width": 150},
        {"label": _("Driver Name"), "fieldname": "full_name", "fieldtype": "Data", "width": 180},
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 150},
        {"label": _("Present Days"), "fieldname": "present_days", "fieldtype": "Int", "width": 110},
        {"label": _("Worked Hours"), "fieldname": "worked_hours", "fieldtype": "Float", "width": 120},
        {"label": _("Fuel Litres"), "fieldname": "fuel_litres", "fieldtype": "Float", "width": 110},
        {"label": _("Fuel Cost"), "fieldname": "fuel_cost", "fieldtype": "Currency", "width": 130},
        {"label": _("Recovered from Driver"), "fieldname": "recovered", "fieldtype": "Currency", "width": 170},
        {"label": _("Net Cost"), "fieldname": "net_cost", "fieldtype": "Currency", "width": 140},
        {"label": _("Cost per Present Day"), "fieldname": "cost_per_present_day", "fieldtype": "Currency", "width": 170},
    ]


def in_scope_drivers(filters):
    driver_filters = {}
    if filters.get("project"):
        driver_filters["project"] = filters["project"]
    if filters.get("driver"):
        driver_filters["name"] = filters["driver"]

    return frappe.get_list(
        "Salis Driver",
        filters=driver_filters,
        fields=["name", "full_name", "project"],
        order_by="name asc",
    )


def get_data(drivers, window, filters):
    names = [driver.name for driver in drivers]

    present_days, worked_hours = {}, {}
    for row in frappe.get_list(
        "Driver Attendance",
        filters={"driver": ["in", names], "attendance_date": window},
        fields=["driver", "status", "worked_hours"],
    ):
        if row.status == "Present":
            present_days[row.driver] = present_days.get(row.driver, 0) + 1
        worked_hours[row.driver] = worked_hours.get(row.driver, 0.0) + flt(row.worked_hours)

    fuel_litres, fuel_cost = {}, {}
    for row in frappe.get_list(
        "Fuel Consumption Ledger",
        filters={"driver": ["in", names], "logged_at": window},
        fields=["driver", "sum(litres) as litres", "sum(amount) as amount"],
        group_by="driver",
    ):
        fuel_litres[row.driver] = flt(row.litres)
        fuel_cost[row.driver] = flt(row.amount)

    recovery_filters = {
        "driver": ["in", names],
        "docstatus": 1,
        "status": "Recovered",
        "request_date": window,
    }
    if filters.get("company"):
        recovery_filters["company"] = filters["company"]

    recovered = {}
    for row in frappe.get_list(
        "Movement Cost Recovery",
        filters=recovery_filters,
        fields=["driver", "sum(amount) as amount"],
        group_by="driver",
    ):
        recovered[row.driver] = flt(row.amount)

    data = []
    for driver in drivers:
        fuel = fuel_cost.get(driver.name, 0.0)
        back = recovered.get(driver.name, 0.0)
        net = fuel - back
        days = present_days.get(driver.name, 0)
        data.append({
            "driver": driver.name,
            "full_name": driver.full_name or "",
            "project": driver.project or "",
            "present_days": days,
            "worked_hours": flt(worked_hours.get(driver.name, 0.0), 2),
            "fuel_litres": flt(fuel_litres.get(driver.name, 0.0), 2),
            "fuel_cost": flt(fuel, 2),
            "recovered": flt(back, 2),
            "net_cost": flt(net, 2),
            "cost_per_present_day": flt(net / days, 2) if days else 0.0,
        })

    data.sort(key=lambda row: row["net_cost"], reverse=True)
    return data


def get_report_summary(data):
    return [
        count_card(_("Drivers"), data),
        total_card(_("Present Days"), data, "present_days", "Int"),
        total_card(_("Fuel Cost"), data, "fuel_cost", "Currency"),
        total_card(_("Net Cost"), data, "net_cost", "Currency"),
    ]


def build_chart(data):
    top = [row for row in data if row["net_cost"]][:10]
    if not top:
        return None
    return {
        "type": "bar",
        "data": {
            "labels": [row["full_name"] or row["driver"] for row in top],
            "datasets": [{"name": _("Net Cost"), "values": [row["net_cost"] for row in top]}],
        },
    }
