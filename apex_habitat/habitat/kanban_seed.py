"""Seed native Frappe Kanban Board records for the two state-driven, writable-status
DocTypes where a drag-to-progress board materially helps daily triage:

- Accommodation Resident Request (intake -> resolution): non-submittable, status writable.
- Maintenance Request: status writable (drag is most useful at the working stage).

Kanban needs no DocType schema change — a board is a "Kanban Board" record bound to
(reference_doctype, status field) with one column per status value. Boards are public
(private = 0) and idempotent: created only if absent, so admins can edit them freely.
"""

import json

import frappe

# board name -> (reference doctype, status field, [(status value, indicator colour), ...])
_BOARDS = [
    {
        "name": "Resident Requests",
        "reference_doctype": "Accommodation Resident Request",
        "field_name": "status",
        "columns": [
            ("New", "Gray"),
            ("Triaged", "Cyan"),
            ("Assigned", "Blue"),
            ("In Progress", "Orange"),
            ("Waiting Evidence", "Yellow"),
            ("Resolved", "Green"),
            ("Rejected", "Red"),
            ("Closed", "Green"),
        ],
    },
    {
        "name": "Maintenance Requests",
        "reference_doctype": "Maintenance Request",
        "field_name": "status",
        "columns": [
            ("Open", "Blue"),
            ("Assigned", "Cyan"),
            ("In Progress", "Orange"),
            ("Resolved", "Green"),
            ("Closed", "Gray"),
            ("Reopened", "Red"),
        ],
    },
]


def seed_kanban_boards():
    """Create the operational Kanban Boards if absent. Safe to re-run."""
    for cfg in _BOARDS:
        if frappe.db.exists("Kanban Board", cfg["name"]):
            continue
        if not frappe.db.exists("DocType", cfg["reference_doctype"]):
            continue
        doc = frappe.get_doc({
            "doctype": "Kanban Board",
            "kanban_board_name": cfg["name"],
            "reference_doctype": cfg["reference_doctype"],
            "field_name": cfg["field_name"],
            "private": 0,
            "show_labels": 1,
            "filters": "[]",
        })
        for column_name, indicator in cfg["columns"]:
            doc.append("columns", {
                "column_name": column_name,
                "status": "Active",
                "indicator": indicator,
                "order": json.dumps([]),
            })
        doc.insert(ignore_permissions=True)  # audit-ok
    frappe.db.commit()
