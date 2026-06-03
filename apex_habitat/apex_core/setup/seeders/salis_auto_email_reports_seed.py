"""Seed native Frappe Auto Email Reports that email an existing Salis Script Report
on a schedule. These are the periodic movement/fleet operational digests:

- Fuel Reconciliation         — Monthly (Finance / Fleet Manager)
- Cost Recovery Aging         — Weekly  (Finance — chase open recoveries)
- Transport Fulfilment SLA    — Weekly  (Fleet Manager — service-level watch)
- Vehicle Compliance Register — Monthly (Government Relations — renewals)

Mirrors ``habitat/auto_email_reports_seed.py``. An Auto Email Report must name a
real recipient; the customer's users/emails are unknown at install, so each is
created **disabled** with Administrator as the placeholder user/recipient. An
admin sets the real recipients and enables it. Idempotent — created only if
absent, and existence-guarded on the report so a partially installed module never
aborts migrate.
"""

import frappe

_REPORTS = [
    {"report": "Fuel Reconciliation", "frequency": "Monthly"},
    {"report": "Cost Recovery Aging", "frequency": "Weekly"},
    {"report": "Transport Fulfilment SLA", "frequency": "Weekly"},
    {"report": "Vehicle Compliance Register", "frequency": "Monthly"},
]


def seed_salis_auto_email_reports():
    """Create the Salis operational Auto Email Reports if absent, disabled,
    addressed to Administrator as a placeholder. Safe to re-run.

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
