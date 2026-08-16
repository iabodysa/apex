# Copyright (c) 2026, afmcoltd
"""Safety Task Catalog is master data: a Safety Officer may read it and nothing more, its seed file
and its live rows carry no client or accreditation-vendor name, and an entry needs a code and a
frequency.

The catalog's own ``test_records.json`` is deliberately NOT declared as a dependency here. Its
autoname is ``naming_series:`` while ``task_code`` carries a unique index, so ``make_test_objects``
mints a new docname on every rebuild and the code collides rather than being skipped — the same
trap ERPNext's Project fixture carries. Declaring it would leave a suite that passes until the day
someone clears ``sites/<site>/.test_log``. Nothing in this file needs the row, so nothing declares
it, nor does it carry a sixteen-line ``test_ignore`` block for masters the catalog does not link
to.
"""

from __future__ import annotations

import os

import frappe
from frappe.tests.utils import FrappeTestCase

_CONFIDENTIAL_TOKENS = ("ama" + "zon", "ave" + "tta")
_SEED_JSON = os.path.join(
    frappe.get_app_path("apex"), "apex_core", "setup", "data", "habitat", "safety_task_catalog.json"
)


class TestSafetyTaskCatalog(FrappeTestCase):
    def test_a_safety_officer_may_read_the_master_and_nothing_more(self):
        roles = {p.role: p for p in frappe.get_meta("Safety Task Catalog").permissions}

        self.assertIn("Safety Officer", roles, "the Safety Officer perm row is missing")
        officer = roles["Safety Officer"]
        self.assertEqual(officer.read, 1)
        self.assertFalse(getattr(officer, "write", 0), "Safety Officer must NOT have write")
        self.assertFalse(getattr(officer, "create", 0), "Safety Officer must NOT have create")

    def test_the_seed_file_names_no_client(self):
        with open(_SEED_JSON, encoding="utf-8") as handle:
            blob = handle.read().lower()

        for token in _CONFIDENTIAL_TOKENS:
            self.assertNotIn(token, blob, f"confidential token '{token}' leaked into the seed JSON")

    def test_no_live_row_names_a_client(self):
        rows = frappe.get_all("Safety Task Catalog", fields=["task_code", "task_title", "instructions"])

        for row in rows:
            blob = " ".join(str(row.get(field) or "") for field in row).lower()
            for token in _CONFIDENTIAL_TOKENS:
                self.assertNotIn(
                    token, blob,
                    f"confidential token '{token}' present in row {row.get('task_code')}",
                )

    def test_an_entry_takes_the_code_it_is_given(self):
        entry = frappe.get_doc({
            "doctype": "Safety Task Catalog",
            "naming_series": "STC-.####",
            "task_code": "_T-STC-QA-001",
            "task_title": "Check fire extinguishers",
            "department": "Fire Safety",
            "frequency": "Monthly",
        })
        entry.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Safety Task Catalog", entry.name, force=True, ignore_permissions=True
        )

        self.assertEqual(entry.task_code, "_T-STC-QA-001")

    def test_an_entry_without_a_code_is_refused(self):
        entry = frappe.get_doc({
            "doctype": "Safety Task Catalog",
            "naming_series": "STC-.####",
            "task_title": "Inspect exits",
            "department": "Fire Safety",
            "frequency": "Daily",
        })

        with self.assertRaises(frappe.exceptions.MandatoryError):
            entry.insert(ignore_permissions=True)

    def test_an_entry_saved_without_a_frequency_silently_becomes_a_daily_task(self):
        """A required Select left empty is not caught by the mandatory check.

        ``frequency`` is a required Select, and Frappe fills a required Select with the FIRST of
        its options when it is left empty — so the mandatory pass never fires and the entry is
        saved as Daily. That is a live safety consequence, not a test detail: a round nobody chose
        a cadence for enters the schedule as a daily one.
        """
        entry = frappe.get_doc({
            "doctype": "Safety Task Catalog",
            "naming_series": "STC-.####",
            "task_code": "_T-STC-QA-999",
            "task_title": "Inspect exits",
            "department": "Security",
        })
        entry.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Safety Task Catalog", entry.name, force=True, ignore_permissions=True
        )

        self.assertEqual(entry.frequency, "Daily")
