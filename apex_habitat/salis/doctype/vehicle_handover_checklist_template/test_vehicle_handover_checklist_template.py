# Copyright (c) 2026, AFMCO and contributors
"""Tests for loading a Vehicle Handover Checklist Template into a handover."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.doctype.vehicle_handover_checklist_template.vehicle_handover_checklist_template import (
    load_template_into_doc,
)


class TestVehicleHandoverChecklistTemplate(FrappeTestCase):
    def setUp(self):
        suffix = frappe.generate_hash(length=6)

        self.vehicle = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": f"CHK {suffix}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name

        # Active driver with no linked Employee is clearance-clear.
        self.driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": f"Checklist Driver {suffix}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name

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
                "vehicle": self.vehicle,
                "to_driver": self.driver,
                "handover_date": frappe.utils.today(),
            }
        ).insert(ignore_permissions=True).name

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
        # Falsify the draft guard: submit the handover, then expect a rejection.
        doc = frappe.get_doc("Vehicle Handover", self.handover)
        doc.odometer_reading = 100
        doc.signed_evidence = "/files/dummy-evidence.png"
        doc.submit()
        with self.assertRaises(frappe.ValidationError):
            load_template_into_doc(handover=self.handover, template=self.template)
