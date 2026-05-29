"""Seed native Frappe Assignment Rules that auto-create ToDos for incoming Salis
(movement/fleet) work, routing it to the responsible division owner:

- Transport Request (Round Robin) — give movement-division intake an owner.
- Support Ticket (Load Balancing) — distribute support tickets across the team.

These cannot ship with a real team list (the customer's division-owner users are
unknown), so each rule is created **disabled** with Administrator as a single
placeholder assignee. An admin must replace the users with their real division
owners (e.g. the Workers-Transport and Representatives-Fleet leads) and enable
the rule. Idempotent and existence-guarded on the document type — created only
if absent, never fatal on a partially installed module.
"""

import frappe

_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_RULES = [
    {
        "name": "Salis - Transport Request Routing",
        "document_type": "Transport Request",
        "rule": "Round Robin",
        "assign_condition": "status == 'New'",
        "description": (
            "Auto-assign new transport requests to the responsible division owner "
            "(round robin). DISABLED by default: replace the placeholder user with "
            "your real Workers-Transport / Representatives-Fleet division owners, "
            "then enable."
        ),
    },
    {
        "name": "Salis - Support Ticket Routing",
        "document_type": "Support Ticket",
        "rule": "Load Balancing",
        "assign_condition": "status == 'New'",
        "description": (
            "Auto-assign new support tickets across the division support team "
            "(load balancing). DISABLED by default: replace the placeholder user "
            "with your real support team, then enable."
        ),
    },
]


def seed_salis_assignment_rules():
    """Create the Salis operational Assignment Rules if absent, disabled, with an
    Administrator placeholder assignee. Existence-guarded; safe to re-run."""
    for cfg in _RULES:
        if frappe.db.exists("Assignment Rule", cfg["name"]):
            continue
        if not frappe.db.exists("DocType", cfg["document_type"]):
            continue
        doc = frappe.get_doc({
            "doctype": "Assignment Rule",
            "name": cfg["name"],
            "document_type": cfg["document_type"],
            "rule": cfg["rule"],
            "disabled": 1,
            "description": cfg["description"],
            "assign_condition": cfg["assign_condition"],
            "priority": 0,
        })
        doc.append("users", {"user": "Administrator"})
        for day in _DAYS:
            doc.append("assignment_days", {"day": day})
        doc.insert(ignore_permissions=True)  # audit-ok
    frappe.db.commit()
