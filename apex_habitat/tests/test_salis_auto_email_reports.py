"""Functional guard for the Salis Auto Email Report seeder.

The seeder is the declarative delivery path for the periodic movement/fleet
digests; it must create each report disabled (the email kill-switch) and keyed on
its report link so re-running is idempotent. This focuses on the daily
fleet-status digest (Salis Fleet Register), which managers rely on for a daily
snapshot.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.apex_core.setup.seeders.salis_auto_email_reports_seed import (
    seed_salis_auto_email_reports,
)

DAILY_REPORT = "Salis Fleet Register"


class TestSalisAutoEmailReportSeeder(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # Clear the marker row so the seeder's create-if-absent path is exercised
        # on a fresh or re-run site (global write — keep this test self-contained).
        existing = frappe.db.get_value("Auto Email Report", {"report": DAILY_REPORT})
        if existing:
            frappe.delete_doc("Auto Email Report", existing, force=True)
            frappe.db.commit()

    def test_seeds_daily_fleet_status_digest_disabled(self):
        # The digest's underlying report must be registered on the bench.
        self.assertTrue(frappe.db.exists("Report", DAILY_REPORT))

        seed_salis_auto_email_reports()

        aer = frappe.db.get_value(
            "Auto Email Report",
            {"report": DAILY_REPORT},
            ["frequency", "enabled", "report_type"],
            as_dict=True,
        )
        self.assertIsNotNone(aer, "daily fleet-status Auto Email Report was not seeded")
        self.assertEqual(aer.frequency, "Daily")
        # Disabled by default — nothing is emailed until an admin enables it and
        # the master notification toggle is on.
        self.assertFalse(aer.enabled)
        self.assertEqual(aer.report_type, "Script Report")

    def test_reseed_is_idempotent(self):
        seed_salis_auto_email_reports()
        seed_salis_auto_email_reports()
        rows = frappe.get_all("Auto Email Report", filters={"report": DAILY_REPORT})
        self.assertEqual(len(rows), 1, "seeder must create exactly one digest per report")

    def test_daily_digest_report_renders_columns(self):
        # The digest produces a real fleet-status report (columns at minimum;
        # rows depend on site data and may legitimately be empty on a fresh site).
        columns, _data = frappe.get_attr(
            "apex_habitat.salis.report.salis_fleet_register.salis_fleet_register.execute"
        )(None)
        fieldnames = {c["fieldname"] for c in columns}
        self.assertIn("status", fieldnames)
        self.assertIn("plate_normalized", fieldnames)
