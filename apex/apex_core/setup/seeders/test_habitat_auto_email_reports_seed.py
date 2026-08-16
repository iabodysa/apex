# Copyright (c) 2026, AFMCO and contributors
"""Functional guard for the Habitat Auto Email Report seeder.

Mirrors the Salis sibling's own test (``test_salis_auto_email_reports.py``):
each declared report must be created DISABLED (the email kill-switch) and
keyed on its report link so re-running is idempotent. Focuses on one report
(Maintenance Aging, Weekly) rather than all four -- the shared base function
is what actually walks the list, and it is exercised identically for every
entry.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup.seeders.habitat_auto_email_reports_seed import (
    seed_auto_email_reports,
)

WEEKLY_REPORT = "Maintenance Aging"


class TestHabitatAutoEmailReportSeeder(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # A test body may delete + COMMIT the seeded row, escaping the FrappeTestCase
        # rollback; re-seed unconditionally on cleanup so the shared DB always carries
        # the canonical digests, mirroring the Salis seeder test's own guard.
        self.addCleanup(self._restore_seeded_reports)

    @staticmethod
    def _restore_seeded_reports():
        frappe.set_user("Administrator")
        seed_auto_email_reports()
        frappe.db.commit()

    def test_seeds_maintenance_aging_digest_disabled(self):
        self.assertTrue(frappe.db.exists("Report", WEEKLY_REPORT))

        seed_auto_email_reports()

        aer = frappe.db.get_value(
            "Auto Email Report",
            {"report": WEEKLY_REPORT},
            ["frequency", "enabled", "user"],
            as_dict=True,
        )
        self.assertIsNotNone(aer, "Maintenance Aging Auto Email Report was not seeded")
        self.assertEqual(aer.frequency, "Weekly")
        self.assertFalse(aer.enabled)
        self.assertEqual(aer.user, "Administrator")

    def test_reseed_is_idempotent(self):
        seed_auto_email_reports()
        seed_auto_email_reports()
        rows = frappe.get_all("Auto Email Report", filters={"report": WEEKLY_REPORT})
        self.assertEqual(len(rows), 1, "seeder must create exactly one digest per report")
