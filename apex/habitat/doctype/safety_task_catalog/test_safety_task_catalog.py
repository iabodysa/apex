# Copyright (c) 2026, afmcoltd
"""Tests for Safety Task Catalog's source-provenance guard.

Patterned on frappe/tests/test_document.py. The row is built directly and
inserted so ``validate`` in ``safety_task_catalog.py`` is what is exercised,
not a stub.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSafetyTaskCatalogSourceProvenanceGuard(FrappeTestCase):
    def test_a_worker_facing_field_carrying_a_source_filename_is_refused(self):
        doc = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "naming_series": "STC-.####",
                "task_title": "Fire Drill Steps imported_from_master.xlsx",
                "department": "Fire Safety",
                "task_code": "_T-STC-GUARD",
                "frequency": "Monthly",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
