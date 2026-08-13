from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from apex.salis.doctype.vehicle_handover import vehicle_handover


class TestVehicleHandoverChecklist(unittest.TestCase):
    def setUp(self):
        frappe.local.flags = frappe._dict(in_test=False)
        frappe.local.request = None
        frappe.local.db = MagicMock()

    def _doc(self, **values):
        data = {
            "direction": "Return",
            "vehicle": "VEH-1",
            "checklist_template": "Daily Inspection",
            "handover_check_items": [
                SimpleNamespace(check_item="Tyres", ok=1, remark=""),
                SimpleNamespace(check_item="Lights", ok=0, remark="Cracked"),
            ],
        }
        data.update(values)
        return SimpleNamespace(**data)

    @patch.object(vehicle_handover, "_", side_effect=lambda message: message)
    @patch.object(
        vehicle_handover.frappe, "throw", side_effect=frappe.ValidationError
    )
    def test_receipt_cannot_bypass_native_checklist(self, _throw, _translate):
        doc = self._doc(direction="Receipt", checklist_template=None)

        with self.assertRaises(frappe.ValidationError):
            vehicle_handover.VehicleHandover._validate_native_checklist(doc)

    @patch.object(vehicle_handover, "_", side_effect=lambda message: message)
    @patch.object(
        vehicle_handover.frappe, "throw", side_effect=frappe.ValidationError
    )
    @patch.object(vehicle_handover.frappe.db, "get_value", return_value="Bus")
    @patch.object(vehicle_handover.frappe, "get_doc")
    def test_checklist_rows_must_exactly_match_active_applicable_template(
        self, get_doc, _category, _throw, _translate
    ):
        get_doc.return_value = SimpleNamespace(
            name="Daily Inspection",
            is_active=1,
            vehicle_category="Bus",
            items=[
                SimpleNamespace(check_item="Tyres"),
                SimpleNamespace(check_item="Lights"),
            ],
        )
        doc = self._doc(
            handover_check_items=[
                SimpleNamespace(check_item="Tyres", ok=1, remark="")
            ]
        )

        with self.assertRaises(frappe.ValidationError):
            vehicle_handover.VehicleHandover._validate_native_checklist(doc)

    @patch.object(vehicle_handover, "_", side_effect=lambda message: message)
    @patch.object(
        vehicle_handover.frappe, "throw", side_effect=frappe.ValidationError
    )
    @patch.object(vehicle_handover.frappe.db, "get_value", return_value="Bus")
    @patch.object(vehicle_handover.frappe, "get_doc")
    def test_inactive_checklist_cannot_be_used(
        self, get_doc, _category, _throw, _translate
    ):
        get_doc.return_value = SimpleNamespace(
            name="Retired Inspection",
            is_active=0,
            vehicle_category="Bus",
            items=[SimpleNamespace(check_item="Tyres")],
        )

        with self.assertRaises(frappe.ValidationError):
            vehicle_handover.VehicleHandover._validate_native_checklist(
                self._doc()
            )

    @patch.object(vehicle_handover, "_", side_effect=lambda message: message)
    @patch.object(
        vehicle_handover.frappe, "throw", side_effect=frappe.ValidationError
    )
    @patch.object(vehicle_handover.frappe.db, "get_value", return_value="Bus")
    @patch.object(vehicle_handover.frappe, "get_doc")
    def test_checklist_for_another_vehicle_category_cannot_be_used(
        self, get_doc, _category, _throw, _translate
    ):
        get_doc.return_value = SimpleNamespace(
            name="Sedan Inspection",
            is_active=1,
            vehicle_category="Sedan",
            items=[SimpleNamespace(check_item="Tyres")],
        )

        with self.assertRaises(frappe.ValidationError):
            vehicle_handover.VehicleHandover._validate_native_checklist(
                self._doc()
            )

    @patch.object(vehicle_handover.frappe.db, "get_value", return_value="Bus")
    @patch.object(vehicle_handover.frappe, "get_doc")
    def test_exact_active_applicable_checklist_is_accepted(self, get_doc, _category):
        get_doc.return_value = SimpleNamespace(
            name="Daily Inspection",
            is_active=1,
            vehicle_category="Bus",
            items=[
                SimpleNamespace(check_item="Tyres"),
                SimpleNamespace(check_item="Lights"),
            ],
        )

        vehicle_handover.VehicleHandover._validate_native_checklist(self._doc())


if __name__ == "__main__":
    unittest.main()
