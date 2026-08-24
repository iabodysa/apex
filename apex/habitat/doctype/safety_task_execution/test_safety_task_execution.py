# Copyright (c) 2026, afmcoltd
"""Tests for Safety Task Execution's evidence-photo guard.

Patterned on frappe/tests/test_document.py. The row is built directly and
inserted so ``validate``'s ``_enforce_evidence`` in
``safety_task_execution.py`` is what is exercised, not a stub.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]


class TestSafetyTaskExecutionEvidenceGuard(FrappeTestCase):
    def test_a_failed_result_on_an_evidence_required_task_without_a_photo_is_refused(self):
        catalog = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "naming_series": "STC-.####",
                "task_title": "_T-STE Guard Task",
                "department": "Fire Safety",
                "task_code": "_T-STE-GUARD",
                "frequency": "Monthly",
                "evidence_required": 1,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Safety Task Catalog", catalog.name, ignore_permissions=True, force=True
            )
        )

        doc = frappe.get_doc(
            {
                "doctype": "Safety Task Execution",
                "naming_series": "STE-.YYYY.-.#####",
                "execution_date": "2026-03-01",
                "building": "_Test Building",
                "task": catalog.name,
                "execution_status": "Poor",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)
