# Copyright (c) 2026, AFMCO and contributors
"""Seed native Frappe Auto Email Reports that email an existing Salis Script Report
on a schedule. These are the periodic movement/fleet operational digests:

- Fleet Register              — Daily   (Fleet Managers — fleet-status snapshot)
- Fuel Reconciliation         — Monthly (Finance / Fleet Manager)
- Cost Recovery Aging         — Weekly  (Finance — chase open recoveries)
- Transport Fulfilment SLA    — Weekly  (Fleet Manager — service-level watch)
- Vehicle Compliance Register — Monthly (Government Relations — renewals)

Mirrors ``habitat_auto_email_reports_seed.py``. An Auto Email Report must name a
real recipient; the customer's users/emails are unknown at install, so each is
created **disabled** with Administrator as the placeholder user/recipient. An
admin sets the real recipients and enables it. Idempotent — created only if
absent, and existence-guarded on the report so a partially installed module never
aborts migrate.

Email kill-switch: seeding these **disabled** is the gate for this declarative
path — nothing is sent until an admin both enables the individual report AND
turns on the master ``enable_email_notifications`` toggle in Habitat Settings
(``apex_core.utils.email_gate.email_enabled``). We never seed them enabled, so
the master toggle being OFF by default is upheld here without extra logic.
"""

from apex.apex_core.setup.seeders.auto_email_report_seed_base import seed_auto_email_reports_for

_REPORTS = [
    {"report": "Fleet Register", "frequency": "Daily"},
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
    seed_auto_email_reports_for(_REPORTS)
