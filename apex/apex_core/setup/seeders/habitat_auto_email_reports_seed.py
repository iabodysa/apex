# Copyright (c) 2026, afmcoltd

from apex.apex_core.setup.seeders.auto_email_report_seed_base import seed_auto_email_reports_for

_REPORTS = [
    {"report": "Supplier Cost Recovery", "frequency": "Monthly"},
    {"report": "Accommodation Occupancy Summary", "frequency": "Weekly"},
    {"report": "Maintenance Aging", "frequency": "Weekly"},
    {"report": "Safety Open Findings", "frequency": "Weekly"},
]


def seed_auto_email_reports():
    seed_auto_email_reports_for(_REPORTS)
