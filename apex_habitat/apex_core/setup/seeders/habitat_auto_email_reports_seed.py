# Copyright (c) 2026, AFMCO and contributors
"""Seed native Frappe Auto Email Reports that email an existing Script Report on a
schedule. These are the periodic operational digests:

- Supplier Cost Recovery  — Monthly (Finance)
- Occupancy Trend         — Weekly  (Accommodation Manager)
- Maintenance Backlog     — Weekly  (fills the gap that escalation only logs)
- Scheduled Task Compliance — Weekly (Resident Supervisor)

An Auto Email Report must name a real recipient; the customer's users/emails are
unknown at install, so each is created **disabled** with Administrator as the
placeholder user/recipient. An admin sets the real recipients and enables it.
Idempotent — created only if absent.

Email kill-switch: seeding these **disabled** is the gate for this declarative
path — nothing is sent until an admin both enables the individual report AND
turns on the master ``enable_email_notifications`` toggle in Habitat Settings
(``apex_core.utils.email_gate.email_enabled``). We never seed them enabled, so
the master toggle being OFF by default is upheld here without extra logic.
"""

import frappe

_REPORTS = [
    {"report": "Supplier Cost Recovery", "frequency": "Monthly"},
    {"report": "Occupancy Trend", "frequency": "Weekly"},
    {"report": "Maintenance Backlog", "frequency": "Weekly"},
    {"report": "Scheduled Task Compliance", "frequency": "Weekly"},
]


def seed_auto_email_reports():
    """Create the operational Auto Email Reports if absent, disabled, addressed to
    Administrator as a placeholder. Safe to re-run.

    Auto Email Report auto-names from its report, so idempotency is keyed on the
    `report` link (one scheduled email per report), not a synthetic name."""
    admin_email = frappe.db.get_value("User", "Administrator", "email") or "admin@example.com"
    for cfg in _REPORTS:
        if frappe.db.exists("Auto Email Report", {"report": cfg["report"]}):
            continue
        if not frappe.db.exists("Report", cfg["report"]):
            continue
        report_type = frappe.db.get_value("Report", cfg["report"], "report_type")
        doc = frappe.get_doc({
            "doctype": "Auto Email Report",
            "report": cfg["report"],
            "report_type": report_type,
            "user": "Administrator",
            "enabled": 0,
            "email_to": admin_email,
            "format": "HTML",
            "frequency": cfg["frequency"],
            "data_modified_till": 0,
            "no_of_rows": 100,
        })
        doc.insert(ignore_permissions=True)  # audit-ok
    frappe.db.commit()
