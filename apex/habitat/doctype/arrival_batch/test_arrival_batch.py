# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]


class TestArrivalBatchComputedFields(FrappeTestCase):
    def test_expected_count_and_title_are_derived_from_the_worker_rows(self):
        doc = frappe.get_doc(
            {
                "doctype": "Arrival Batch",
                "naming_series": "ARR-BATCH-.YYYY.-.####",
                "building": "_Test Building",
                "expected_date": "2026-03-01",
                "expected_workers": [
                    {"worker_name": "_T-Worker One"},
                    {"worker_name": "_T-Worker Two"},
                ],
            }
        )
        doc.insert(ignore_permissions=True)
        self.addCleanup(
            lambda name=doc.name: frappe.delete_doc(
                "Arrival Batch", name, ignore_permissions=True, force=True
            )
        )
        self.assertEqual(doc.expected_count, 2)
        self.assertIn("_Test Building", doc.title)


class TestArrivalBatchGuestIntake(FrappeTestCase):
    def test_a_guest_submission_cannot_name_the_temporary_worker_a_row_already_is(self):
        worker = frappe.get_doc(
            {
                "doctype": "Temporary Worker",
                "naming_series": "TEMP-.YYYY.-.#####",
                "worker_name": "_T-Manifest Temp Worker",
                "passport_number": "_T-P9000001",
                "arrival_date": "2026-01-01",
                "status": "Active",
                "window_days": 30,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(
            lambda name=worker.name: frappe.delete_doc(
                "Temporary Worker", name, ignore_permissions=True, force=True
            )
        )
        frappe.set_user("Guest")
        self.addCleanup(frappe.set_user, "Administrator")
        doc = frappe.get_doc(
            {
                "doctype": "Arrival Batch",
                "naming_series": "ARR-BATCH-.YYYY.-.####",
                "building": "_Test Building",
                "expected_date": "2026-03-01",
                "expected_workers": [
                    {"worker_name": "_T-Worker One", "temporary_worker": worker.name},
                ],
            }
        )
        doc.insert(ignore_permissions=True)
        self.addCleanup(
            lambda name=doc.name: frappe.delete_doc(
                "Arrival Batch", name, ignore_permissions=True, force=True
            )
        )
        self.assertIsNone(doc.expected_workers[0].temporary_worker)
