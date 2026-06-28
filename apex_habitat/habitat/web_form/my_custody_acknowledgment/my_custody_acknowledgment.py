# Copyright (c) 2026, AFMCO and contributors
"""My Custody Acknowledgment Web Form context.

Per-user, login-required form. Pre-fills the Custody Issue from an ``?issue=``
query param (the link a supervisor shares / a QR resolves to) and exposes the
caller's own submitted, not-yet-acknowledged issues so the holder can pick the
right one. The acknowledgment is written to its own Custody Acknowledgment
target, never onto the Custody Issue.
"""

import frappe


def get_context(context):
    # Renders per-user with live data; never serve a cached copy.
    context.no_cache = 1

    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")

    # Issues already acknowledged by anyone — excluded from the holder's picklist.
    acknowledged = {
        a.custody_issue
        for a in frappe.get_all(
            "Custody Acknowledgment", fields=["custody_issue"], filters={"docstatus": ["<", 2]}
        )
    }

    my_issues = []
    if employee:
        for ci in frappe.get_all(
            "Custody Issue",
            filters={"issued_to_employee": employee, "docstatus": 1, "status": "Issued"},
            fields=["name", "issue_date", "building"],
            order_by="issue_date desc",
        ):
            if ci.name not in acknowledged:
                my_issues.append(ci)

    context.my_custody_issues = my_issues
    context.prefill_issue = frappe.form_dict.get("issue") or (my_issues[0].name if my_issues else "")
