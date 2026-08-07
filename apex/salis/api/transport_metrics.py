# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.utils import get_first_day, today


@frappe.whitelist()
def get_transport_requests_served_pct(filters=None):
    frappe.has_permission("Transport Request", "read", throw=True)
    month_start = str(get_first_day(today()))
    raised = frappe.db.count("Transport Request", {"pickup_datetime": [">=", month_start]})
    if not raised:
        return {"value": 100.0, "fieldtype": "Percent", "precision": 1}
    if not frappe.db.exists("DocType", "Trip Fulfilment Ledger"):
        return {"value": 0.0, "fieldtype": "Percent", "precision": 1}
    served = len(set(frappe.get_all(
        "Trip Fulfilment Ledger",
        filters={"trip_date": [">=", month_start], "transport_request": ["is", "set"]},
        pluck="transport_request",
    )))
    return {"value": round(served / raised * 100, 1), "fieldtype": "Percent", "precision": 1}
