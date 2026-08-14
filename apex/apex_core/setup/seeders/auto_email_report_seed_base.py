# Copyright (c) 2026, afmcoltd
"""Shared engine for the per-module Auto Email Report seeders.

The insert passes ``ignore_permissions`` because a seeder is installer context: it runs from
install and migrate as Administrator, with no session user whose roles could be consulted.

Each module ships its own periodic-digest list (Habitat's accommodation/safety
digests, Salis's movement/fleet digests) but the create-if-absent routine is one
rule, so it lives here once and the module seeders keep only their report list.

Two fields are resolved at RUNTIME rather than declared as constants (the
Administrator's email, and each report's ``report_type``), which is why this
stays a code seeder instead of externalised seed JSON.

Email kill-switch: every report is created **disabled** with Administrator as
the placeholder recipient — the customer's real users are unknown at install.
Nothing is sent until an admin both enables the individual report AND turns on
the master ``enable_email_notifications`` toggle in Habitat Settings
(``apex_core.utils.email_gate.email_enabled``), so seeding never has to reason
about the master toggle itself.
"""

import frappe


def seed_auto_email_reports_for(reports):
    """Create each ``{"report", "frequency"}`` entry as a disabled Auto Email Report
    if absent, addressed to Administrator as a placeholder. Safe to re-run.

    Auto Email Report auto-names from its report, so idempotency is keyed on the
    `report` link (one scheduled email per report), not a synthetic name. A report
    that is not installed is skipped, so a partially installed module never aborts
    migrate."""
    admin_email = frappe.db.get_value("User", "Administrator", "email") or "admin@example.com"
    for cfg in reports:
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
        doc.insert(ignore_permissions=True)
    frappe.db.commit()
