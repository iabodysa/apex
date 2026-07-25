# Copyright (c) 2026, AFMCO and contributors
"""Functional guard for the Salis Auto Email Report seeder.

The seeder is the declarative delivery path for the periodic movement/fleet
digests; it must create each report disabled (the email kill-switch) and keyed on
its report link so re-running is idempotent. This focuses on the daily
fleet-status digest (Fleet Register), which managers rely on for a daily
snapshot.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup.seeders.salis_auto_email_reports_seed import (
    seed_salis_auto_email_reports,
)

DAILY_REPORT = "Fleet Register"


class TestSalisAutoEmailReportSeeder(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # A test body may delete + COMMIT the seeded delivery row, which escapes the
        # FrappeTestCase rollback; re-seed unconditionally on cleanup so the shared DB
        # is never left without the canonical digests. Registered in setUp so a
        # mid-test failure still restores. [#cld9yf]
        self.addCleanup(self._restore_seeded_reports)

    @staticmethod
    def _restore_seeded_reports():
        """Reinstate the declarative Auto Email Report rows; the seeder is idempotent."""
        frappe.set_user("Administrator")
        seed_salis_auto_email_reports()
        frappe.db.commit()

    def test_seeds_daily_fleet_status_digest_disabled(self):
        # [#j7r0m6]
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
        # [#er4wsv]
        self.assertFalse(aer.enabled)
        self.assertEqual(aer.report_type, "Script Report")

    def test_reseed_is_idempotent(self):
        seed_salis_auto_email_reports()
        seed_salis_auto_email_reports()
        rows = frappe.get_all("Auto Email Report", filters={"report": DAILY_REPORT})
        self.assertEqual(len(rows), 1, "seeder must create exactly one digest per report")

    def test_daily_digest_report_renders_columns(self):
        # [#4u2hr7]
        columns, _data = frappe.get_attr(
            "apex.salis.report.fleet_register.fleet_register.execute"
        )(None)
        fieldnames = {c["fieldname"] for c in columns}
        self.assertIn("status", fieldnames)
        self.assertIn("plate_normalized", fieldnames)

    def test_restore_reinstates_seed_after_committed_delete(self):
        # Proves the cleanup path heals the exact leak the old setUp caused: hard-delete
        # + COMMIT the digest (escaping the FrappeTestCase rollback), then restore and
        # assert it is back. Fails if the restore path (re-seed) ever regresses. The
        # setUp-registered addCleanup re-seeds again as a backstop.
        existing = frappe.db.get_value("Auto Email Report", {"report": DAILY_REPORT})
        if existing:
            frappe.delete_doc("Auto Email Report", existing, force=True)
            frappe.db.commit()
        self.assertFalse(
            frappe.db.exists("Auto Email Report", {"report": DAILY_REPORT}),
            "precondition: committed delete removed the seeded digest",
        )
        self._restore_seeded_reports()
        self.assertTrue(
            frappe.db.exists("Auto Email Report", {"report": DAILY_REPORT}),
            "cleanup must reinstate the seeded Fleet Register digest",
        )
