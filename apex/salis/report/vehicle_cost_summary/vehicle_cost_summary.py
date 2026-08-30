# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _
from frappe.utils import date_diff, flt

from apex.apex_core.utils.report_summary import card, count_card, total_card


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if not (from_date and to_date):
        frappe.throw(_("From Date and To Date are required."))

    vehicles = in_scope_vehicles(filters)
    if not vehicles:
        return columns, [], None, None, get_report_summary([], 0)

    period_days = max(date_diff(to_date, from_date) + 1, 1)
    data = get_data(vehicles, ["between", [from_date, to_date]], period_days, filters)
    return columns, data, None, build_chart(data), get_report_summary(data, period_days)


def get_columns():
    return [
        {"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 150},
        {"label": _("Plate"), "fieldname": "plate_number", "fieldtype": "Data", "width": 130},
        {"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 150},
        {"label": _("Fuel Litres"), "fieldname": "fuel_litres", "fieldtype": "Float", "width": 110},
        {"label": _("Fuel Cost"), "fieldname": "fuel_cost", "fieldtype": "Currency", "width": 130},
        {"label": _("Rental Cost"), "fieldname": "rental_cost", "fieldtype": "Currency", "width": 130},
        {"label": _("Recovered"), "fieldname": "recovered", "fieldtype": "Currency", "width": 130},
        {"label": _("Net Cost"), "fieldname": "net_cost", "fieldtype": "Currency", "width": 140},
        {"label": _("Cost per Day"), "fieldname": "cost_per_day", "fieldtype": "Currency", "width": 130},
    ]


def in_scope_vehicles(filters):
    vehicle_filters = {}
    for field in ("company", "project"):
        if filters.get(field):
            vehicle_filters[field] = filters[field]
    if filters.get("vehicle"):
        vehicle_filters["name"] = filters["vehicle"]

    return frappe.get_list(
        "Salis Vehicle",
        filters=vehicle_filters,
        fields=["name", "plate_number", "company", "project"],
        order_by="name asc",
    )


def get_data(vehicles, window, period_days, filters):
    names = [vehicle.name for vehicle in vehicles]

    fuel_litres, fuel_cost = {}, {}
    for row in frappe.get_all(
        "Fuel Consumption Ledger",
        filters={"vehicle": ["in", names], "logged_at": window},
        fields=["vehicle", "sum(litres) as litres", "sum(amount) as amount"],
        group_by="vehicle",
    ):
        fuel_litres[row.vehicle] = flt(row.litres)
        fuel_cost[row.vehicle] = flt(row.amount)

    rental_cost = {}
    for row in frappe.get_all(
        "Rental Accrual Ledger",
        filters={"vehicle": ["in", names], "accrual_date": window},
        fields=["vehicle", "sum(amount) as amount"],
        group_by="vehicle",
    ):
        rental_cost[row.vehicle] = flt(row.amount)

    recovery_filters = {
        "vehicle": ["in", names],
        "docstatus": 1,
        "status": "Recovered",
        "request_date": window,
    }
    if filters.get("company"):
        recovery_filters["company"] = filters["company"]

    recovered = {}
    for row in frappe.get_all(
        "Movement Cost Recovery",
        filters=recovery_filters,
        fields=["vehicle", "sum(amount) as amount"],
        group_by="vehicle",
    ):
        recovered[row.vehicle] = flt(row.amount)

    data = []
    for vehicle in vehicles:
        fuel = fuel_cost.get(vehicle.name, 0.0)
        rental = rental_cost.get(vehicle.name, 0.0)
        back = recovered.get(vehicle.name, 0.0)
        net = fuel + rental - back
        data.append({
            "vehicle": vehicle.name,
            "plate_number": vehicle.plate_number or "",
            "company": vehicle.company or "",
            "project": vehicle.project or "",
            "fuel_litres": flt(fuel_litres.get(vehicle.name, 0.0), 2),
            "fuel_cost": flt(fuel, 2),
            "rental_cost": flt(rental, 2),
            "recovered": flt(back, 2),
            "net_cost": flt(net, 2),
            "cost_per_day": flt(net / period_days, 2),
        })

    data.sort(key=lambda row: row["net_cost"], reverse=True)
    return data


def get_report_summary(data, period_days):
    net = sum(flt(row.get("net_cost")) for row in data)
    return [
        count_card(_("Vehicles"), data),
        total_card(_("Fuel Cost"), data, "fuel_cost", "Currency"),
        total_card(_("Rental Cost"), data, "rental_cost", "Currency"),
        total_card(_("Net Cost"), data, "net_cost", "Currency"),
        card(_("Fleet Cost per Day"), flt(net / period_days, 2) if period_days else 0.0, "Currency"),
    ]


def build_chart(data):
    top = [row for row in data if row["net_cost"]][:10]
    if not top:
        return None
    return {
        "type": "bar",
        "data": {
            "labels": [row["plate_number"] or row["vehicle"] for row in top],
            "datasets": [
                {"name": _("Fuel Cost"), "values": [row["fuel_cost"] for row in top]},
                {"name": _("Rental Cost"), "values": [row["rental_cost"] for row in top]},
            ],
        },
    }
