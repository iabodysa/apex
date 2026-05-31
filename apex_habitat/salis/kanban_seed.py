"""Seed native Frappe Kanban Board records for the two state-driven Salis
(movement/fleet) DocTypes where a drag-to-progress board materially helps daily
triage:

- Transport Request (intake -> fulfilment): status-driven workflow.
- Issue (raised -> closed): native ERPNext Issue, status-driven (the Salis
  support board now rides on Issue; the custom Support Ticket was retired).

Kanban needs no DocType schema change — a board is a "Kanban Board" record bound
to (reference_doctype, status field) with one column per status value. Boards are
public (private = 0) and idempotent: created only if absent, so admins can edit
them freely. Existence-guarded on the reference DocType so a partially installed
module never aborts migrate.

Status values + colours are verified against ``salis/doctype/*/*.json``:
- Transport Request.status: New|Validated|Approved|Scheduled|Fulfilled|Rejected|Cancelled
- Issue.status: Open|Replied|On Hold|Resolved|Closed
"""

import json

import frappe

# board name -> (reference doctype, status field, [(status value, indicator colour), ...])
_BOARDS = [
    {
        "name": "Transport Requests",
        "reference_doctype": "Transport Request",
        "field_name": "status",
        "columns": [
            ("New", "Gray"),
            ("Validated", "Cyan"),
            ("Approved", "Blue"),
            ("Scheduled", "Orange"),
            ("Fulfilled", "Green"),
            ("Rejected", "Red"),
            ("Cancelled", "Gray"),
        ],
    },
    {
        "name": "Support Tickets",
        "reference_doctype": "Issue",
        "field_name": "status",
        "columns": [
            ("Open", "Gray"),
            ("Replied", "Orange"),
            ("On Hold", "Yellow"),
            ("Resolved", "Green"),
            ("Closed", "Gray"),
        ],
    },
]


def seed_salis_kanban_boards():
    """Create the Salis operational Kanban Boards if absent. Safe to re-run."""
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
