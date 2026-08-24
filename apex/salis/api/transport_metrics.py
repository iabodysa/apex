# Copyright (c) 2026, afmcoltd
import frappe
from frappe.utils import get_first_day, today

from apex.salis import permissions


@frappe.whitelist()
def get_transport_requests_served_pct(filters=None):
    frappe.has_permission("Transport Request", "read", throw=True)
    tr_filters = {"pickup_datetime": [">=", str(get_first_day(today()))]}
    restrict, allowed = permissions.report_project_scope(frappe.session.user, doctype="Transport Request")
    if restrict:
        if not allowed:
            return {"value": 100.0, "fieldtype": "Percent", "precision": 1}
        tr_filters["project"] = ["in", allowed]
    raised = frappe.get_all("Transport Request", filters=tr_filters, pluck="name")
    if not raised:
        return {"value": 100.0, "fieldtype": "Percent", "precision": 1}
    if not frappe.db.exists("DocType", "Trip Fulfilment Ledger"):
        return {"value": 0.0, "fieldtype": "Percent", "precision": 1}
    served = set(
        frappe.get_all(
            "Trip Fulfilment Ledger",
            filters={"transport_request": ["in", raised], "reversal_of": ["is", "not set"]},
            pluck="transport_request",
        )
    )
    return {"value": round(len(served) / len(raised) * 100, 1), "fieldtype": "Percent", "precision": 1}
