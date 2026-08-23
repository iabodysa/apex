# Copyright (c) 2026, afmcoltd
"""Tests for Vehicle Handover's direction guards, checklist-derived state, and
the default handover time.

Patterned on frappe/tests/test_document.py. Each case builds an unsaved
Document via frappe.new_doc. The direction-requirement cases call the whole
``validate()`` with a direction/driver combination that throws before any
database-backed helper (the assignment lookup, the checklist template, the
rider-block query) is reached, so no fixtures are needed to prove them.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestVehicleHandoverDirectionGuards(FrappeTestCase):
    def _handover(self, **fields):
        doc = frappe.new_doc("Vehicle Handover")
        doc.update(fields)
        return doc

    def test_a_transfer_requires_both_a_from_driver_and_a_to_driver(self):
        doc = self._handover(direction="Transfer", from_driver="D-1", to_driver=None)
        self.assertRaises(frappe.ValidationError, doc.validate)

    def test_blank_direction_defaults_to_transfer_and_carries_its_requirement(self):
        doc = self._handover(direction=None, from_driver="D-1", to_driver=None)
        self.assertRaises(frappe.ValidationError, doc.validate)
        self.assertEqual(doc.direction, "Transfer")

    def test_a_receipt_requires_a_to_driver(self):
        doc = self._handover(direction="Receipt", to_driver=None)
        self.assertRaises(frappe.ValidationError, doc.validate)

    def test_a_receipt_clears_any_from_driver(self):
        doc = self._handover(direction="Receipt", from_driver="D-1", to_driver=None)
        with self.assertRaises(frappe.ValidationError):
            doc.validate()
        self.assertIsNone(doc.from_driver)

    def test_a_return_requires_a_from_driver(self):
        doc = self._handover(direction="Return", from_driver=None)
        self.assertRaises(frappe.ValidationError, doc.validate)

    def test_a_return_clears_any_to_driver(self):
        doc = self._handover(direction="Return", from_driver=None, to_driver="D-2")
        with self.assertRaises(frappe.ValidationError):
            doc.validate()
        self.assertIsNone(doc.to_driver)

    def test_an_unrecognised_direction_is_refused(self):
        doc = self._handover(direction="Sideways")
        self.assertRaises(frappe.ValidationError, doc.validate)


class TestVehicleHandoverDiscrepancyDerivation(FrappeTestCase):
    def _handover(self, direction, rows):
        doc = frappe.new_doc("Vehicle Handover")
        doc.direction = direction
        for row in rows:
            doc.append("handover_check_items", row)
        return doc

    def test_every_check_passing_is_derived_as_clean(self):
        doc = self._handover("Receipt", [{"check_item": "Tyres", "ok": 1}])
        doc._derive_discrepancy()
        self.assertEqual(doc.discrepancy_status, "Clean")
        self.assertIsNone(doc.discrepancy_notes)

    def test_one_failed_check_is_derived_as_a_discrepancy_with_its_remark(self):
        doc = self._handover(
            "Return", [{"check_item": "Tyres", "ok": 0, "remark": "Front-left worn."}]
        )
        doc._derive_discrepancy()
        self.assertEqual(doc.discrepancy_status, "Discrepancy")
        self.assertIn("Tyres", doc.discrepancy_notes)
        self.assertIn("Front-left worn.", doc.discrepancy_notes)

    def test_a_transfer_is_never_graded_by_the_checklist(self):
        """A stale Discrepancy status from before the direction was corrected
        to Transfer must survive unchanged: the derivation only runs for a
        Receipt or a Return, so it must not silently launder a real
        discrepancy into "untouched" just because it happens to also be
        absent."""
        doc = self._handover("Transfer", [{"check_item": "Tyres", "ok": 0}])
        doc.discrepancy_status = "Discrepancy"
        doc.discrepancy_notes = "Pre-existing note."
        doc._derive_discrepancy()
        self.assertEqual(doc.discrepancy_status, "Discrepancy")
        self.assertEqual(doc.discrepancy_notes, "Pre-existing note.")


class TestVehicleHandoverDefaultTime(FrappeTestCase):
    """``frappe.new_doc`` itself stamps every Time field with the current
    clock time (frappe/model/create_new.py:148-149) before the controller
    ever runs, so building the case that way would test the framework, not
    this guard. A payload built via ``frappe.get_doc({...})`` — the shape a
    whitelisted API handler constructs from a request body — carries no such
    stamp, which is exactly the gap ``before_insert`` closes.
    """

    def test_an_unset_handover_time_defaults_at_insert(self):
        doc = frappe.get_doc({"doctype": "Vehicle Handover"})
        self.assertFalse(doc.handover_time)
        doc.before_insert()
        self.assertTrue(doc.handover_time)

    def test_a_caller_supplied_handover_time_is_not_overwritten(self):
        doc = frappe.get_doc(
            {"doctype": "Vehicle Handover", "handover_time": "08:15:00"}
        )
        doc.before_insert()
        self.assertEqual(doc.handover_time, "08:15:00")
