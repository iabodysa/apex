# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.housing_assignment.housing_assignment import (
    _flag_temporary_worker_past_expiry,
    _snapshot_agreed_rate,
)


class TestSnapshotAgreedRate(FrappeTestCase):
    def test_a_blank_rate_is_filled_from_the_buildings_cost_per_bed(self):
        doc = frappe._dict(agreed_monthly_rate=None)
        building = frappe._dict(monthly_cost_per_capacity=850)
        _snapshot_agreed_rate(doc, building)
        self.assertEqual(doc.agreed_monthly_rate, 850)

    def test_an_operator_entered_rate_is_never_overwritten(self):
        doc = frappe._dict(agreed_monthly_rate=1200)
        building = frappe._dict(monthly_cost_per_capacity=850)
        _snapshot_agreed_rate(doc, building)
        self.assertEqual(doc.agreed_monthly_rate, 1200)

    def test_a_building_with_no_configured_rate_leaves_the_field_at_zero(self):
        doc = frappe._dict(agreed_monthly_rate=None)
        building = frappe._dict(monthly_cost_per_capacity=None)
        _snapshot_agreed_rate(doc, building)
        self.assertEqual(doc.agreed_monthly_rate, 0)


class TestFlagTemporaryWorkerPastExpiry(FrappeTestCase):
    def _doc(self, **fields):
        base = {"party_type": "Temporary Worker", "party": "_T-TW-0001", "check_in_date": None}
        base.update(fields)
        return frappe._dict(base)

    def test_a_non_temporary_worker_party_is_never_looked_up(self):
        doc = frappe._dict(party_type="Employee", party="HR-EMP-0001", check_in_date=None)
        with patch.object(frappe.db, "get_value") as mock_get_value:
            _flag_temporary_worker_past_expiry(doc)
            mock_get_value.assert_not_called()

    def test_no_party_named_is_never_looked_up(self):
        doc = frappe._dict(party_type="Temporary Worker", party=None, check_in_date=None)
        with patch.object(frappe.db, "get_value") as mock_get_value:
            _flag_temporary_worker_past_expiry(doc)
            mock_get_value.assert_not_called()

    def test_an_expiry_before_check_in_raises_the_warning(self):
        doc = self._doc(check_in_date="2026-06-01")
        with patch.object(frappe.db, "get_value", return_value="2026-05-01"), patch.object(
            frappe, "msgprint"
        ) as mock_msgprint:
            _flag_temporary_worker_past_expiry(doc)
            mock_msgprint.assert_called_once()
            self.assertEqual(mock_msgprint.call_args.kwargs.get("indicator"), "orange")

    def test_an_expiry_on_or_after_check_in_raises_nothing(self):
        doc = self._doc(check_in_date="2026-06-01")
        with patch.object(frappe.db, "get_value", return_value="2026-07-01"), patch.object(
            frappe, "msgprint"
        ) as mock_msgprint:
            _flag_temporary_worker_past_expiry(doc)
            mock_msgprint.assert_not_called()
