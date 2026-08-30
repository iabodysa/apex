# Copyright (c) 2026, afmcoltd


import frappe
from frappe import _
from frappe.utils import date_diff, getdate, nowdate
from apex.apex_core.utils.report_summary import count_card, total_card

OPEN_STATUSES = ("Open", "Acknowledged", "Approved")

def _bucket(days):
    if days <= 30:
        return "b_0_30"
    if days <= 60:
        return "b_31_60"
    if days <= 90:
        return "b_61_90"
    return "b_90_plus"

def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Recovery"), "fieldname": "name", "fieldtype": "Link", "options": "Movement Cost Recovery", "width": 160},
        {"label": _("Recovery Type"), "fieldname": "recovery_type", "fieldtype": "Data", "width": 140},
        {"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
        {"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 140},
        {"label": _("Driver"), "fieldname": "driver", "fieldtype": "Link", "options": "Salis Driver", "width": 140},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 140},
        {"label": _("Payment Request"), "fieldname": "payment_request", "fieldtype": "Link", "options": "Salis Payment Request", "width": 160},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
        {"label": _("Request Date"), "fieldname": "request_date", "fieldtype": "Date", "width": 120},
        {"label": _("Age (Days)"), "fieldname": "age_days", "fieldtype": "Int", "width": 100},
        {"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
        {"label": _("0-30"), "fieldname": "b_0_30", "fieldtype": "Currency", "width": 110},
        {"label": _("31-60"), "fieldname": "b_31_60", "fieldtype": "Currency", "width": 110},
        {"label": _("61-90"), "fieldname": "b_61_90", "fieldtype": "Currency", "width": 110},
        {"label": _("90+"), "fieldname": "b_90_plus", "fieldtype": "Currency", "width": 110},
    ]

    if not frappe.db.exists("DocType", "Movement Cost Recovery"):
        return columns, []

    query_filters = {}
    for field in ("company", "recovery_type", "vehicle", "driver", "employee"):
        if filters.get(field):
            query_filters[field] = filters[field]
    if filters.get("status"):
        query_filters["status"] = filters["status"]
    else:
        query_filters["status"] = ["in", list(OPEN_STATUSES)]

    records = frappe.get_list(
        "Movement Cost Recovery",
        filters=query_filters,
        fields=["name", "recovery_type", "company", "vehicle", "driver", "employee", "payment_request", "status", "request_date", "amount"],
        order_by="request_date asc",
    )

    as_on = getdate(filters.get("as_on_date") or nowdate())

    data = []
    totals = {
        "name": _("Total"),
        "recovery_type": "",
        "company": "",
        "vehicle": "",
        "driver": "",
        "employee": "",
        "payment_request": "",
        "status": "",
        "request_date": None,
        "age_days": None,
        "amount": 0.0,
        "b_0_30": 0.0,
        "b_31_60": 0.0,
        "b_61_90": 0.0,
        "b_90_plus": 0.0,
    }

    for rec in records:
        amount = rec.get("amount") or 0.0
        request_date = rec.get("request_date")
        age = date_diff(as_on, getdate(request_date)) if request_date else 0
        if age < 0:
            age = 0
        row = {
            "name": rec.get("name"),
            "recovery_type": rec.get("recovery_type"),
            "company": rec.get("company"),
            "vehicle": rec.get("vehicle"),
            "driver": rec.get("driver"),
            "employee": rec.get("employee"),
            "payment_request": rec.get("payment_request"),
            "status": rec.get("status"),
            "request_date": request_date,
            "age_days": age,
            "amount": amount,
            "b_0_30": 0.0,
            "b_31_60": 0.0,
            "b_61_90": 0.0,
            "b_90_plus": 0.0,
        }
        bucket = _bucket(age)
        row[bucket] = amount
        totals[bucket] += amount
        totals["amount"] += amount
        data.append(row)

    summary = [
        count_card(_("Open Recoveries"), data),
        total_card(_("Outstanding"), data, "amount", "Currency"),
        total_card(_("Over 90 Days"), data, "b_90_plus", "Currency", indicator="Red"),
        count_card(_("Aged Over 60 Days"), data, lambda r: (r.get("age_days") or 0) > 60, "Orange"),
    ]

    if data:
        data.append(totals)
    return columns, data, None, _build_chart(totals if data else None), summary

def _build_chart(totals):
    if not totals:
        return None
    buckets = ["b_0_30", "b_31_60", "b_61_90", "b_90_plus"]
    values = [round(totals.get(b) or 0.0, 2) for b in buckets]
    if not any(values):
        return None
    return {
        "type": "bar",
        "data": {
            "labels": [_("0-30"), _("31-60"), _("61-90"), _("90+")],
            "datasets": [{"name": _("Open Exposure"), "values": values}],
        },
    }
