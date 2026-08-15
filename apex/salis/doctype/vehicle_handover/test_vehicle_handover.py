from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import frappe

from apex.salis.doctype.vehicle_handover import vehicle_handover

_UNSET = object()


class TestVehicleHandoverChecklist(unittest.TestCase):
    def setUp(self):
        # frappe.db and frappe.flags are LocalProxy objects over frappe.local, so
        # assigning here replaces them for the entire process, not just this test.
        # Restore them or the next test inherits a mock database and a flags dict
        # that has lost the keys frappe.init seeded.
        saved = {
            name: getattr(frappe.local, name, _UNSET)
            for name in ("flags", "request", "db")
        }
        self.addCleanup(self._restore_frappe_local, saved)
        frappe.local.flags = frappe._dict(in_test=False)
        frappe.local.request = None
        frappe.local.db = MagicMock()

    @staticmethod
    def _restore_frappe_local(saved):
        for name, value in saved.items():
            if value is _UNSET:
                delattr(frappe.local, name)
            else:
                setattr(frappe.local, name, value)

    def _doc(self, **values):
        data = {
            "direction": "Return",
            "vehicle": "VEH-1",
            "vehicle_assignment": "VA-1",
            "checklist_template": "Daily Inspection",
            "handover_check_items": [
                SimpleNamespace(check_item="Tyres", ok=1, remark=""),
                SimpleNamespace(check_item="Lights", ok=0, remark="Cracked"),
            ],
        }
        data.update(values)
        return SimpleNamespace(**data)

    def test_vehicle_assignment_link_is_a_stable_handover_contract(self):
        metadata = json.loads(
            Path(__file__)
            .with_name("vehicle_handover.json")
            .read_text(encoding="utf-8")
        )
        field = next(
            row
            for row in metadata["fields"]
            if row["fieldname"] == "vehicle_assignment"
        )

        self.assertEqual(field["fieldtype"], "Link")
        self.assertEqual(field["options"], "Vehicle Assignment")
        self.assertEqual(field["no_copy"], 1)
        self.assertIn("Receipt", field["mandatory_depends_on"])
        self.assertIn("Return", field["mandatory_depends_on"])

    def test_failed_rows_derive_discrepancy_and_all_pass_clears_it(self):
        handler = getattr(vehicle_handover.VehicleHandover, "_derive_discrepancy", None)
        self.assertIsNotNone(handler)
        failed = self._doc(discrepancy_status="Clean", discrepancy_notes=None)

        handler(failed)

        self.assertEqual(failed.discrepancy_status, "Discrepancy")
        self.assertEqual(failed.discrepancy_notes, "Lights: Cracked")

        passed = self._doc(
            discrepancy_status="Discrepancy",
            discrepancy_notes="Old",
            handover_check_items=[
                SimpleNamespace(check_item="Tyres", ok=1, remark=""),
                SimpleNamespace(check_item="Lights", ok=1, remark=""),
            ],
        )
        handler(passed)
        self.assertEqual(passed.discrepancy_status, "Clean")
        self.assertIsNone(passed.discrepancy_notes)

    @patch.object(vehicle_handover, "lock_vehicle")
    @patch.object(vehicle_handover, "add_timeline_note")
    @patch.object(vehicle_handover, "frappe")
    @patch.object(vehicle_handover, "_", side_effect=lambda message: message)
    def test_return_ends_only_its_linked_assignment(
        self, _translate, frappe, _timeline, _lock_vehicle
    ):
        doc = self._doc(
            name="GV-1",
            from_driver="DRV-1",
            to_driver=None,
            odometer_reading=150,
            handover_date="2026-08-14",
            discrepancy_status="Clean",
            add_comment=MagicMock(),
        )
        frappe.db.get_value.return_value = "VEH-1"

        vehicle_handover.VehicleHandover.on_submit(doc)

        self.assertIn(
            call(
                "Vehicle Assignment",
                "VA-1",
                {"status": "Ended", "end_date": "2026-08-14"},
            ),
            frappe.db.set_value.call_args_list,
        )
        frappe.get_list.assert_not_called()

    @patch.object(vehicle_handover, "lock_vehicle")
    @patch.object(vehicle_handover, "add_timeline_note")
    @patch.object(vehicle_handover, "frappe")
    @patch.object(vehicle_handover, "_", side_effect=lambda message: message)
    def test_receipt_submit_then_cancel_preserves_authoritative_active_assignment(
        self, _translate, frappe, _timeline, _lock_vehicle
    ):
        state = {"vehicle_driver": None, "driver_vehicle": None}
        assignment = SimpleNamespace(
            name="VA-1",
            vehicle="VEH-1",
            driver="DRV-1",
            status="Active",
            docstatus=1,
        )
        frappe.get_doc.return_value = assignment

        def get_value(doctype, _name, fieldname):
            if (doctype, fieldname) == ("Salis Vehicle", "current_driver"):
                return state["vehicle_driver"]
            if (doctype, fieldname) == ("Salis Driver", "current_vehicle"):
                return state["driver_vehicle"]
            return None

        def set_value(doctype, _name, fieldname, value=None, **_kwargs):
            updates = fieldname if isinstance(fieldname, dict) else {fieldname: value}
            if doctype == "Salis Vehicle" and "current_driver" in updates:
                state["vehicle_driver"] = updates["current_driver"]
            if doctype == "Salis Driver" and "current_vehicle" in updates:
                state["driver_vehicle"] = updates["current_vehicle"]

        frappe.db.get_value.side_effect = get_value
        frappe.db.set_value.side_effect = set_value
        doc = self._doc(
            name="GV-1",
            direction="Receipt",
            from_driver=None,
            to_driver="DRV-1",
            odometer_reading=150,
            handover_date="2026-08-14",
            discrepancy_status="Clean",
            add_comment=MagicMock(),
        )

        vehicle_handover.VehicleHandover.on_submit(doc)

        self.assertEqual(state["vehicle_driver"], "DRV-1")
        self.assertEqual(state["driver_vehicle"], "VEH-1")
        state.update(vehicle_driver=None, driver_vehicle=None)
        frappe.db.set_value.reset_mock()

        vehicle_handover.VehicleHandover.on_cancel(doc)

        self.assertEqual(state["vehicle_driver"], "DRV-1")
        self.assertEqual(state["driver_vehicle"], "VEH-1")
        self.assertIn(
            call("Salis Vehicle", "VEH-1", "current_driver", "DRV-1"),
            frappe.db.set_value.call_args_list,
        )
        self.assertIn(
            call("Salis Driver", "DRV-1", "current_vehicle", "VEH-1"),
            frappe.db.set_value.call_args_list,
        )
        frappe.get_doc.assert_called_once_with(
            "Vehicle Assignment", "VA-1", for_update=True
        )

    @patch.object(vehicle_handover, "_", side_effect=lambda message: message)
    @patch.object(vehicle_handover.frappe, "throw", side_effect=frappe.ValidationError)
    @patch.object(vehicle_handover.frappe.db, "get_value", return_value="GV-OLD")
    @patch.object(vehicle_handover.frappe, "get_doc")
    def test_assignment_lock_serializes_one_receipt_per_direction(
        self, get_doc, get_value, _throw, _translate
    ):
        get_doc.return_value = SimpleNamespace(
            name="VA-1",
            vehicle="VEH-1",
            driver="DRV-1",
            status="Active",
            docstatus=1,
        )
        doc = self._doc(
            name="GV-NEW",
            direction="Receipt",
            from_driver=None,
            to_driver="DRV-1",
        )

        with self.assertRaises(frappe.ValidationError):
            vehicle_handover.VehicleHandover._validate_assignment_event(doc)

        get_doc.assert_called_once_with("Vehicle Assignment", "VA-1", for_update=True)
        filters = get_value.call_args.args[1]
        self.assertEqual(filters["vehicle_assignment"], "VA-1")
        self.assertEqual(filters["direction"], "Receipt")
        self.assertEqual(filters["docstatus"], 1)

    @patch.object(vehicle_handover, "_", side_effect=lambda message: message)
    @patch.object(vehicle_handover.frappe, "throw", side_effect=frappe.ValidationError)
    @patch.object(vehicle_handover.frappe.db, "get_value", return_value=None)
    @patch.object(vehicle_handover.frappe, "get_doc")
    def test_assignment_must_match_event_vehicle_and_driver(
        self, get_doc, _duplicate, _throw, _translate
    ):
        get_doc.return_value = SimpleNamespace(
            name="VA-1",
            vehicle="VEH-OTHER",
            driver="DRV-1",
            status="Active",
            docstatus=1,
        )

        with self.assertRaises(frappe.ValidationError):
            vehicle_handover.VehicleHandover._validate_assignment_event(
                self._doc(from_driver="DRV-1")
            )

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
