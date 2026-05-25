"""Seed native Frappe Assignment Rules that auto-create ToDos for incoming work:

- Maintenance Request (Load Balancing) — distribute new requests across the team.
- Accommodation Resident Request (Round Robin) — give web-form intake an owner.

These cannot ship with a real team list (the customer's users are unknown), so
each rule is created **disabled** with Administrator as a single placeholder
assignee. An admin must replace the users with their real maintenance/triage team
and enable the rule. Idempotent — created only if absent.
"""

import frappe

_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_RULES = [
    {
        "name": "Habitat - Maintenance Request Intake",
        "document_type": "Maintenance Request",
        "rule": "Load Balancing",
        "assign_condition": "status == 'Open'",
        "description": (
            "Auto-assign new maintenance requests across the maintenance team. "
            "DISABLED by default: replace the placeholder user with your real team, "
            "then enable."
        ),
    },
    {
        "name": "Habitat - Resident Request Triage",
        "document_type": "Accommodation Resident Request",
        "rule": "Round Robin",
        "assign_condition": "status == 'New'",
        "description": (
            "Auto-assign new resident requests to a triage owner (round robin). "
            "DISABLED by default: replace the placeholder user with your real triage "
            "team, then enable."
        ),
    },
]


def seed_assignment_rules():
    """Create the operational Assignment Rules if absent, disabled, with an
    Administrator placeholder assignee. Safe to re-run."""
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
