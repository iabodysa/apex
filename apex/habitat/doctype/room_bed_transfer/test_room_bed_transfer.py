# Copyright (c) 2026, afmcoltd
"""Tests for Room Bed Transfer's source-building resolution and its
cross-building refusal.

Patterned on test_lease.py. ``_source_building`` and the cross-building
branch of ``validate`` each read one or two Link targets via
``frappe.db.get_value``; those reads are mocked by return value so the
"prefer the live assignment's building, fall back to the origin bed's" and
"refuse a move that would cross buildings" decisions are exercised without a
live Housing Assignment/Bed/Room. ``assignment`` is left unset in the
``validate`` cases so ``sync_party_employee``'s own ``derive_from`` lookup
(a separate DB read outside this controller's own logic) never fires.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.room_bed_transfer.room_bed_transfer import (
    _source_building,
    validate,
)


class TestSourceBuilding(FrappeTestCase):
    def test_the_live_assignments_building_wins(self):
        doc = frappe._dict(assignment="HA-0001", from_bed=None)
        with patch.object(
            frappe.db, "get_value", return_value="_Test Building"
        ) as mock_get_value:
            self.assertEqual(_source_building(doc), "_Test Building")
            mock_get_value.assert_called_once_with("Housing Assignment", "HA-0001", "building")

    def test_no_assignment_falls_back_to_the_origin_beds_building(self):
        doc = frappe._dict(assignment=None, from_bed="_T-101-A")
        with patch.object(
            frappe.db, "get_value", return_value="_Test Building"
        ) as mock_get_value:
            self.assertEqual(_source_building(doc), "_Test Building")
            mock_get_value.assert_called_once_with("Bed", "_T-101-A", "building")

    def test_neither_source_returns_none(self):
        doc = frappe._dict(assignment=None, from_bed=None)
        with patch.object(frappe.db, "get_value") as mock_get_value:
            self.assertIsNone(_source_building(doc))
            mock_get_value.assert_not_called()

    def test_the_assignment_wins_even_when_a_from_bed_is_also_given(self):
        doc = frappe._dict(assignment="HA-0001", from_bed="_T-101-A")
        with patch.object(
            frappe.db, "get_value", return_value="_Test Building"
        ) as mock_get_value:
            self.assertEqual(_source_building(doc), "_Test Building")
            mock_get_value.assert_called_once_with("Housing Assignment", "HA-0001", "building")


class TestValidateCrossBuildingRefusal(FrappeTestCase):
    def _doc(self, **fields):
        doc = frappe.new_doc("Room Bed Transfer")
        doc.update(fields)
        return doc

    def test_a_move_that_would_cross_buildings_is_refused(self):
        doc = self._doc(to_bed="_T-201-A", to_room="_T-201", from_bed="_T-101-A")
        values = iter(["Available", "_T-201", "_Test Building 2", "_Test Building"])
        with patch.object(frappe.db, "get_value", side_effect=lambda *a, **k: next(values)):
            with self.assertRaises(frappe.ValidationError):
                validate(doc)

    def test_a_move_within_the_same_building_passes(self):
        doc = self._doc(to_bed="_T-102-A", to_room="_T-102", from_bed="_T-101-A")
        values = iter(["Available", "_T-102", "_Test Building", "_Test Building"])
        with patch.object(frappe.db, "get_value", side_effect=lambda *a, **k: next(values)):
            validate(doc)
