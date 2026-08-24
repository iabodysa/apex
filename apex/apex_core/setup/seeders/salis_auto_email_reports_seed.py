# Copyright (c) 2026, afmcoltd

from apex.apex_core.setup.seeders.auto_email_report_seed_base import seed_auto_email_reports_for

_REPORTS = [
    {"report": "Vehicle Assignment Register", "frequency": "Daily"},
    {"report": "Fuel Reconciliation", "frequency": "Monthly"},
    {"report": "Cost Recovery Aging", "frequency": "Weekly"},
    {"report": "Worker Transport Plan", "frequency": "Weekly"},
    {"report": "Vehicle Compliance Register", "frequency": "Monthly"},
]


def seed_salis_auto_email_reports():
    seed_auto_email_reports_for(_REPORTS)
