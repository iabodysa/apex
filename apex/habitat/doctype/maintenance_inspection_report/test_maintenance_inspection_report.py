# Copyright (c) 2026, afmcoltd
"""Tests for Maintenance Inspection Report's cancellation-reason guard.

Patterned on frappe/tests/test_document.py for the cancel guard. The row is
built, submitted and cancelled so the module-level ``before_cancel`` in
``maintenance_inspection_report.py`` -- wired through hooks.py's doc_events,
not the class body -- is what is exercised, not a stub.

``Maintenance Work Order`` and ``Facility Asset`` are excluded from the
dependency walk: no case here sets either, and each one's own closure
resolves an unmigrated ``Payment Gateway`` and kills record-building before
a single test runs.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import purge_doc

test_dependencies = ["Building", "Employee"]
test_ignore = ["Maintenance Work Order", "Facility Asset"]


class TestMaintenanceInspectionReportCancelGuard(FrappeTestCase):
    def test_cancelling_without_a_reason_is_refused(self):
        doc = frappe.get_doc(
            {
                "doctype": "Maintenance Inspection Report",
                "inspection_date": "2026-03-01",
                "building": "_Test Building",
                "inspector": "_T-Employee-00001",
                "findings": [{"description": "_T-Cracked tile in corridor"}],
            }
        )
        doc.insert(ignore_permissions=True)
        doc.submit()
        self.addCleanup(purge_doc, "Maintenance Inspection Report", doc.name)
        with self.assertRaises(frappe.ValidationError):
            doc.cancel()
