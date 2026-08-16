# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Facility Asset Movement Ledger's single-write immutability guard.

One row is posted per submitted Facility Asset Movement by the asset movement
engine, and a reversal is a separate negated row on cancel -- never an edit of the
original. ``validate()`` is the only thing standing between that design and a
posted relocation record being silently altered after the fact, so it is exercised
directly: insert must pass (``is_new()`` is True), and any later save of the SAME
row must be refused (``is_new()`` is False).
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestFacilityAssetMovementLedger(FrappeTestCase):
    def _make_row(self):
        return frappe.get_doc(
            {
                "doctype": "Facility Asset Movement Ledger",
                "posting_datetime": frappe.utils.now_datetime(),
                "from_location": "Store A",
                "to_location": "Store B",
            }
        ).insert(ignore_permissions=True)

    def test_the_initial_insert_is_allowed(self):
        row = self._make_row()
        self.assertTrue(frappe.db.exists("Facility Asset Movement Ledger", row.name))

    def test_editing_an_already_persisted_row_is_refused(self):
        row = self._make_row()
        loaded = frappe.get_doc("Facility Asset Movement Ledger", row.name)
        loaded.to_location = "Store C"
        with self.assertRaises(frappe.PermissionError):
            loaded.save(ignore_permissions=True)

    def test_the_row_is_unchanged_after_the_refused_edit(self):
        row = self._make_row()
        loaded = frappe.get_doc("Facility Asset Movement Ledger", row.name)
        loaded.to_location = "Store C"
        with self.assertRaises(frappe.PermissionError):
            loaded.save(ignore_permissions=True)
        self.assertEqual(
            frappe.db.get_value("Facility Asset Movement Ledger", row.name, "to_location"),
            "Store B",
        )
