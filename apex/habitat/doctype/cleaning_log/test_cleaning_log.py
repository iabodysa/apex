# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.tests.factories import make_building


def _evidenced_log(building, **overrides):
    fields = {
        "doctype": "Cleaning Log",
        "building": building,
        "cleaning_date": today(),
        "cleaner_type": "Internal Employee",
        "area_photos": [
            {"area": "Bathrooms", "status": "Cleaned", "photo": "/files/bathroom.jpg"},
            {"area": "Kitchen", "status": "Cleaned", "photo": "/files/kitchen.jpg"},
            {"area": "Corridors", "status": "Not Cleaned", "note": "Locked wing"},
        ],
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestCleaningLogAreaEvidence(FrappeTestCase):
    def test_submitting_without_evidence_for_a_required_area_is_refused(self):
        building = make_building("_T-Cleaning Log Missing Area")
        doc = _evidenced_log(
            building.name,
            area_photos=[
                {"area": "Bathrooms", "status": "Cleaned", "photo": "/files/bathroom.jpg"},
                {"area": "Kitchen", "status": "Cleaned", "photo": "/files/kitchen.jpg"},
            ],
        ).insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "is required before submit"):
            doc.submit()

    def test_submitting_a_cleaned_area_with_no_photo_and_no_excuse_is_refused(self):
        building = make_building("_T-Cleaning Log No Photo")
        doc = _evidenced_log(
            building.name,
            area_photos=[
                {"area": "Bathrooms", "status": "Cleaned"},
                {"area": "Kitchen", "status": "Cleaned", "photo": "/files/kitchen.jpg"},
                {"area": "Corridors", "status": "Not Cleaned", "note": "Locked wing"},
            ],
        ).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            doc.submit()

    def test_submitting_with_every_required_area_evidenced_succeeds(self):
        building = make_building("_T-Cleaning Log Full Evidence")
        doc = _evidenced_log(building.name).insert(ignore_permissions=True)
        doc.submit()
        self.assertEqual(doc.docstatus, 1)

    def test_a_cleaned_photo_row_is_stamped_with_captured_at_on_submit(self):
        building = make_building("_T-Cleaning Log Stamp")
        doc = _evidenced_log(building.name).insert(ignore_permissions=True)
        doc.submit()
        bathroom_row = next(r for r in doc.area_photos if r.area == "Bathrooms")
        self.assertIsNotNone(bathroom_row.captured_at)
