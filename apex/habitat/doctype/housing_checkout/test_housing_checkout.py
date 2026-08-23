# Copyright (c) 2026, afmcoltd
"""Tests for Housing Checkout's damage-assessment building fallback and its
server-authoritative damage-deduction rollup.

Patterned on test_lease.py: neither helper inserts a document. The rollup
runs on an unsaved Housing Checkout with its child table populated via
``doc.append`` -- no DB row is ever written. The building fallback's one DB
read (``frappe.db.get_value("Bed", ...)``) is mocked so the "assignment
carries no building, fall back to the bed's" branch is exercised without a
live Bed.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.housing_checkout.housing_checkout import (
    _roll_up_damage_deduction,
    resolve_damage_assessment_building,
)


class TestResolveDamageAssessmentBuilding(FrappeTestCase):
    def test_the_submitted_assignments_own_building_wins(self):
        assignment = frappe._dict(building="_Test Building")
        with patch.object(frappe.db, "get_value") as mock_get_value:
            result = resolve_damage_assessment_building(assignment, "_T-101-A")
            self.assertEqual(result, "_Test Building")
            mock_get_value.assert_not_called()

    def test_a_missing_assignment_building_falls_back_to_the_beds(self):
        assignment = frappe._dict(building=None)
        with patch.object(
            frappe.db, "get_value", return_value="_Test Building 2"
        ) as mock_get_value:
            result = resolve_damage_assessment_building(assignment, "_T-201-A")
            self.assertEqual(result, "_Test Building 2")
            mock_get_value.assert_called_once_with("Bed", "_T-201-A", "building")

    def test_neither_source_returns_none_not_an_empty_string(self):
        assignment = frappe._dict(building=None)
        with patch.object(frappe.db, "get_value", return_value=None):
            result = resolve_damage_assessment_building(assignment, None)
            self.assertIsNone(result)


class TestRollUpDamageDeduction(FrappeTestCase):
    def _doc(self, *amounts):
        doc = frappe.new_doc("Housing Checkout")
        for amount in amounts:
            doc.append("custody_return_items", {"deduction_amount": amount})
        return doc

    def test_the_parent_total_is_the_sum_of_every_child_row(self):
        doc = self._doc(100, 250, 0)
        _roll_up_damage_deduction(doc)
        self.assertEqual(doc.damage_deduction_amount, 350)

    def test_no_rows_totals_to_zero(self):
        doc = self._doc()
        _roll_up_damage_deduction(doc)
        self.assertEqual(doc.damage_deduction_amount, 0)
