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

    my_issues = []
    if employee:
        # This holder's own open, issued custody issues — the picklist candidates.
        candidates = frappe.get_all(
            "Custody Issue",
            filters={"issued_to_employee": employee, "docstatus": 1, "status": "Issued"},
            fields=["name", "issue_date", "building"],
            order_by="issue_date desc",
        )
        # Already-acknowledged subset, scoped to THIS holder's own issues. get_all
        # bypasses permission_query_conditions, so an unfiltered query would read
        # every building's acknowledgments cross-tenant; confining to the holder's
        # own issue names keeps the read to the caller's own data.
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

    # [#own] Only pre-fill from ``?issue=`` when that issue is THIS holder's own.
    # An unchecked URL param would render another employee's Custody Issue to any
    # authenticated caller. A foreign / unknown docname falls back to the holder's
    # first own issue (or blank).
    requested = frappe.form_dict.get("issue")
    own_issue = bool(requested) and frappe.db.get_value(
        "Custody Issue", requested, "issued_to_employee"
    ) == employee
    context.prefill_issue = (
        requested if own_issue else (my_issues[0].name if my_issues else "")
    )
