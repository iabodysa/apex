# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, today, date_diff


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": frappe._("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 180},
        {"label": frappe._("Plate"), "fieldname": "plate_number", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Compliance Type"), "fieldname": "compliance_type", "fieldtype": "Data", "width": 160},
        {"label": frappe._("Document No"), "fieldname": "document_number", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Expiry Date"), "fieldname": "expiry_date", "fieldtype": "Date", "width": 120},
        {"label": frappe._("Days To Expiry"), "fieldname": "days_to_expiry", "fieldtype": "Int", "width": 120},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
    ]

    row_filters = {"parenttype": "Salis Vehicle"}
    if filters.get("status"):
        row_filters["status"] = filters["status"]
    if filters.get("from_date"):
        row_filters["expiry_date"] = [">=", filters["from_date"]]
    if filters.get("to_date"):
        if "expiry_date" in row_filters:
            row_filters["expiry_date"] = ["between", [filters["from_date"], filters["to_date"]]]
        else:
            row_filters["expiry_date"] = ["<=", filters["to_date"]]

    rows = frappe.get_all(
        "Salis Vehicle Compliance",
        filters=row_filters,
        fields=[
            "parent",
            "compliance_type",
            "document_number",
            "expiry_date",
            "status",
        ],
        order_by="expiry_date asc",
    )

    # Bulk plate lookup to avoid N+1
    vehicle_names = list({r["parent"] for r in rows if r.get("parent")})
    plate_map = {}
    if vehicle_names:
        for v in frappe.get_all(
            "Salis Vehicle",
            filters={"name": ["in", vehicle_names]},
            fields=["name", "plate_number"],
        ):
            plate_map[v["name"]] = v.get("plate_number")

    today_date = getdate(today())
    data = []
    for r in rows:
        days_to_expiry = None
        if r.get("expiry_date"):
            days_to_expiry = date_diff(getdate(r["expiry_date"]), today_date)
        data.append(
            {
                "vehicle": r.get("parent"),
                "plate_number": plate_map.get(r.get("parent")),
                "compliance_type": r.get("compliance_type"),
                "document_number": r.get("document_number"),
                "expiry_date": r.get("expiry_date"),
                "days_to_expiry": days_to_expiry,
                "status": r.get("status"),
            }
        )

    return columns, data
