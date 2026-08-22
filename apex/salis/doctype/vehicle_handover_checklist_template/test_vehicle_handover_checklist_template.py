# Copyright (c) 2026, AFMCO and contributors
"""Tests for loading a Vehicle Handover Checklist Template into a handover.

The vehicle and the rider are the shipped fixtures; the template and the handover are the
subject and are still built here. Each case hands the borrowed pair back — the submitted
handover is cancelled and the mirrored driver link cleared.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.doctype.vehicle_handover_checklist_template.vehicle_handover_checklist_template import (
    load_template_into_doc,
)

test_dependencies = ["Salis Vehicle", "Salis Driver"]

PLATE = "_T ABC 1001"
DRIVER_NAME = "_Test Driver"
FROM_DRIVER_NAME = "_Test Driver Two"

class TestVehicleHandoverChecklistTemplate(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        suffix = frappe.generate_hash(length=12)
        self.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": PLATE}, "name")
        self.driver = frappe.db.get_value("Salis Driver", {"full_name": DRIVER_NAME}, "name")
        self.from_driver = frappe.db.get_value(
            "Salis Driver", {"full_name": FROM_DRIVER_NAME}, "name"
        )

        self.template = frappe.get_doc(
            {
                "doctype": "Vehicle Handover Checklist Template",
                "template_name": f"Standard Sedan {suffix}",
                "is_active": 1,
                "items": [
                    {"check_item": "Spare tyre present", "remark": "Inspect tread"},
                    {"check_item": "Fire extinguisher present"},
                ],
            }
        ).insert(ignore_permissions=True).name

        self.handover = frappe.get_doc(
            {
                "doctype": "Vehicle Handover",
                "direction": "Transfer",
                "vehicle": self.vehicle,
                "from_driver": self.from_driver,
                "to_driver": self.driver,
                "handover_date": frappe.utils.today(),
            }
        ).insert(ignore_permissions=True).name
        self.addCleanup(self._restore)

    def _restore(self):
        """Cancel the handover the case may have submitted and clear what it mirrored
        onto the borrowed vehicle and rider."""
        doc = frappe.get_doc("Vehicle Handover", self.handover)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.db.set_value("Salis Vehicle", self.vehicle, "current_driver", None)
        frappe.db.set_value("Salis Driver", self.driver, "current_vehicle", None)

    def test_loads_items_into_handover(self):
        result = load_template_into_doc(handover=self.handover, template=self.template)
        self.assertEqual(result["rows_added"], 2)

        doc = frappe.get_doc("Vehicle Handover", self.handover)
        labels = [row.check_item for row in doc.handover_check_items]
        self.assertEqual(len(labels), 2)
        self.assertIn("Spare tyre present", labels)
        self.assertIn("Fire extinguisher present", labels)

        spare = next(r for r in doc.handover_check_items if r.check_item == "Spare tyre present")
        self.assertEqual(spare.remark, "Inspect tread")

    def test_inactive_template_is_rejected(self):
        frappe.db.set_value(
            "Vehicle Handover Checklist Template", self.template, "is_active", 0
        )
        with self.assertRaises(frappe.ValidationError):
            load_template_into_doc(handover=self.handover, template=self.template)

    def test_only_draft_handover_accepts_a_template(self):
        doc = frappe.get_doc("Vehicle Handover", self.handover)
        doc.odometer_reading = 100
        doc.signed_evidence = "/files/dummy-evidence.png"
        doc.submit()
        with self.assertRaises(frappe.ValidationError):
            load_template_into_doc(handover=self.handover, template=self.template)
