# Copyright (c) 2026, afmcoltd
"""My Custody Acknowledgment Web Form context.

Per-user, login-required form. Pre-fills the Custody Issue from an ``?issue=``
query param (the link a supervisor shares / a QR resolves to) and exposes the
caller's own submitted, not-yet-acknowledged issues so the holder can pick the
right one. The acknowledgment is written to its own Custody Acknowledgment
target, never onto the Custody Issue.
"""

import frappe


def get_context(context):
    """Loads the caller's unacknowledged Custody Issues and pre-fills the one named in the URL."""
    context.no_cache = 1

    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")

    my_issues = []
    if employee:
        candidates = frappe.get_all(
            "Custody Issue",
            filters={"issued_to_employee": employee, "docstatus": 1, "status": "Issued"},
            fields=["name", "issue_date", "building"],
            order_by="issue_date desc",
        )
        candidate_names = [ci.name for ci in candidates]
        acknowledged = (
            {
                a.custody_issue
                for a in frappe.get_all(
                    "Custody Acknowledgment",
                    fields=["custody_issue"],
                    filters={
                        "docstatus": ["<", 2],
                        "custody_issue": ["in", candidate_names],
                    },
                )
            }
            if candidate_names
            else set()
        )
        my_issues = [ci for ci in candidates if ci.name not in acknowledged]

    context.my_custody_issues = my_issues

    requested = frappe.form_dict.get("issue")
    own_issue = bool(requested) and frappe.db.get_value(
        "Custody Issue", requested, "issued_to_employee"
    ) == employee
    context.prefill_issue = (
        requested if own_issue else (my_issues[0].name if my_issues else "")
    )
