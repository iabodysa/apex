# Copyright (c) 2026, AFMCO and contributors
"""Tests for the retired-reports cleanup patch.

One retired report name (from ``RETIRED_REPORTS``) is recreated as a minimal
Query Report, with an Auto Email Report pointed at it and the retired
Onboarding Step, so the patch's three deletions can each be pinned without
depending on whatever a given site still carries from the real migration.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_3.retire_replaced_reports import execute

RETIRED_REPORT = "Fleet Register"
ONBOARDING_STEP = "Review the Active Resident Register"


class TestRetireReplacedReports(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._report_existed = frappe.db.exists("Report", RETIRED_REPORT)
        self._aer_existed = frappe.db.exists(
            "Auto Email Report", {"report": RETIRED_REPORT}
        )
        self._step_existed = frappe.db.exists("Onboarding Step", ONBOARDING_STEP)
        self._created = []

        if not self._report_existed:
            report = frappe.get_doc(
                {
                    "doctype": "Report",
                    "report_name": RETIRED_REPORT,
                    "ref_doctype": "ToDo",
                    "report_type": "Query Report",
                    "is_standard": "No",
                }
            ).insert(ignore_permissions=True)
            self._created.append(("Report", report.name))

        if not self._aer_existed:
            aer = frappe.get_doc(
                {
                    "doctype": "Auto Email Report",
                    "report": RETIRED_REPORT,
                    "user": "Administrator",
                    "email_to": "admin@example.com",
                    "frequency": "Weekly",
                    "format": "HTML",
                }
            ).insert(ignore_permissions=True)
            self._created.append(("Auto Email Report", aer.name))

        if not self._step_existed:
            step = frappe.get_doc(
                {
                    "doctype": "Onboarding Step",
                    "name": ONBOARDING_STEP,
                    "title": ONBOARDING_STEP,
                    "action": "View Report",
                    "reference_report": RETIRED_REPORT,
                }
            ).insert(ignore_permissions=True)
            self._created.append(("Onboarding Step", step.name))

    def tearDown(self):
        # execute() should already have removed all three; nothing survives to clean up
        # unless the test failed mid-way, in which case remove what this setUp added.
        for doctype, name in reversed(self._created):
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True, ignore_missing=True)

    def test_execute_removes_the_report_the_auto_email_report_and_the_onboarding_step(self):
        execute()

        self.assertFalse(frappe.db.exists("Report", RETIRED_REPORT))
        self.assertFalse(frappe.db.exists("Auto Email Report", {"report": RETIRED_REPORT}))
        self.assertFalse(frappe.db.exists("Onboarding Step", ONBOARDING_STEP))

    def test_execute_is_idempotent_on_a_site_that_already_ran_it(self):
        execute()
        execute()  # must not raise on a site where everything is already gone

        self.assertFalse(frappe.db.exists("Report", RETIRED_REPORT))
