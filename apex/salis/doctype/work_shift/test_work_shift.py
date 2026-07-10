# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Work Shift DocType.

Run with:
    bench run-tests --app apex --module apex.salis.doctype.work_shift.test_work_shift
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWorkShift(FrappeTestCase):
    """Smoke tests for Work Shift creation and constraint enforcement."""

    def _make_shift(self, **kwargs):
        """Helper: build and insert a minimal valid Work Shift."""
        doc = frappe.new_doc("Work Shift")
        doc.shift_name = kwargs.get("shift_name", "Test Morning Shift")
        doc.start_date = kwargs.get("start_date", "2026-07-01")
        doc.start_time = kwargs.get("start_time", "06:00:00")
        doc.end_time = kwargs.get("end_time", "14:00:00")
        doc.project = kwargs.get("project", frappe.db.get_value("Project", {}, "name") or "_Test Project")
        doc.is_active = kwargs.get("is_active", 1)
        return doc

    def tearDown(self):
        """Remove any Work Shift documents created during the test run."""
        for name in frappe.get_all("Work Shift", pluck="name"):
            frappe.delete_doc("Work Shift", name, ignore_permissions=True, force=True)

    def test_autoname_pattern(self):
        """A saved Work Shift must be assigned a name starting with WS-."""
        doc = self._make_shift()
        doc.insert(ignore_permissions=True)
        self.assertTrue(
            doc.name.startswith("WS-"),
            f"Expected name to start with 'WS-', got: {doc.name}",
        )

    def test_required_fields_enforced(self):
        """Inserting without shift_name must raise a MandatoryError."""
        doc = self._make_shift()
        doc.shift_name = ""  # clear the required field
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True)
