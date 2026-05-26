# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

"""Movement KPI Summary — a one-glance, ORM-only roll-up of the Movement
operational KPIs surfaced on the Movement Operations Dashboard.

It is defensive about the *new* engine DocTypes (Trip Fulfilment Ledger,
Fuel Consumption Ledger, Rental Accrual Ledger, Vehicle Utilisation Snapshot):
each metric is counted only if its source DocType is migrated, otherwise the
metric is reported as 0 with a "not installed" note rather than raising.

Optional filters: from_date / to_date applied to date-bearing sources.
"""

import frappe


def _has(doctype):
    return bool(frappe.db.exists("DocType", doctype))


def _count(doctype, filters):
    if not _has(doctype):
        return None
    try:
        return frappe.db.count(doctype, filters)
    except Exception:
        return None


def _sum(doctype, field, filters):
    if not _has(doctype):
        return None
    try:
        rows = frappe.get_all(doctype, filters=filters, fields=[f"sum({field}) as total"])
        return (rows[0].get("total") if rows else 0) or 0
    except Exception:
        return None


def _avg(doctype, field, filters):
    if not _has(doctype):
        return None
    try:
        rows = frappe.get_all(doctype, filters=filters, fields=[f"avg({field}) as average"])
        return (rows[0].get("average") if rows else 0) or 0
    except Exception:
        return None


def execute(filters=None):
    filters = filters or {}
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    def date_range(field):
        f = {}
        if from_date and to_date:
            f[field] = ["between", [from_date, to_date]]
        elif from_date:
            f[field] = [">=", from_date]
        elif to_date:
            f[field] = ["<=", to_date]
        return f

    columns = [
        {"label": frappe._("KPI"), "fieldname": "kpi", "fieldtype": "Data", "width": 320},
        {"label": frappe._("Value"), "fieldname": "value", "fieldtype": "Data", "width": 160},
        {"label": frappe._("Note"), "fieldname": "note", "fieldtype": "Data", "width": 280},
    ]

    def row(label, value, missing_doctype=None):
        if value is None:
            return {"kpi": label, "value": "0",
                    "note": frappe._("Source not installed: {0}").format(missing_doctype or "")}
        return {"kpi": label, "value": value, "note": ""}

    # --- Trips (Dispatch Trip exists) ---
    completed_filters = {"status": "Completed"}
    completed_filters.update(date_range("trip_date"))
    total_filters = {}
    total_filters.update(date_range("trip_date"))
    completed = _count("Dispatch Trip", completed_filters)
    total_trips = _count("Dispatch Trip", total_filters)
    fulfilment_rate = (
        round((completed / total_trips) * 100, 1)
        if completed is not None and total_trips else 0
    )

    data = [
        row(frappe._("Completed Dispatch Trips"), completed, "Dispatch Trip"),
        row(frappe._("Total Dispatch Trips"), total_trips, "Dispatch Trip"),
        {"kpi": frappe._("Trip Fulfilment Rate"), "value": f"{fulfilment_rate}%", "note": ""},
        row(frappe._("Pending Transport Requests"),
            _count("Transport Request", {"status": "New"}), "Transport Request"),
        row(frappe._("Inter-City Transport Requests"),
            _count("Transport Request", {"request_type": "Inter-City Relocation"}),
            "Transport Request"),
        row(frappe._("Open Fuel Exception Cases"),
            _count("Fuel Exception Case", {"status": "Open"}), "Fuel Exception Case"),
        # Engine-backed KPIs (guarded).
        row(frappe._("Trip Fulfilment Ledger Rows"),
            _count("Trip Fulfilment Ledger", date_range("trip_date")),
            "Trip Fulfilment Ledger"),
        row(frappe._("Fuel Consumption (Litres)"),
            _sum("Fuel Consumption Ledger", "litres", date_range("period_month")),
            "Fuel Consumption Ledger"),
        row(frappe._("Rental Accrual (Amount)"),
            _sum("Rental Accrual Ledger", "amount", date_range("period_month")),
            "Rental Accrual Ledger"),
        row(frappe._("Average Vehicle Utilisation %"),
            _avg("Vehicle Utilisation Snapshot", "utilisation_pct", {}),
            "Vehicle Utilisation Snapshot"),
    ]

    return columns, data
