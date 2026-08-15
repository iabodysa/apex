# Copyright (c) 2026, AFMCO and contributors
"""What a saved Work Shift is named, and which fields the insert refuses without.

The sibling ``test_work_shift.py`` grades the time and applicable-day rules against
``validate`` alone. This module inserts, so it covers the two things only a real insert
can show: the ``WS-.####`` naming series actually mints a name, and ``shift_name``
carries its mandatory flag through to the write.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWorkShiftNaming(FrappeTestCase):
    def _shift(self, **overrides):
        """A Work Shift the controller accepts: ``applicable_days`` is mandatory, so a
        shift with no day never reaches the naming series."""
        values = {
            "doctype": "Work Shift",
            "shift_name": "Naming Morning Shift",
            "start_time": "06:00:00",
            "end_time": "14:00:00",
            "applicable_days": [{"day_of_week": "Monday"}],
        }
        values.update(overrides)
        return frappe.get_doc(values)

    def _insert(self, doc):
        doc.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Work Shift", doc.name, ignore_permissions=True, force=True
        )
        return doc

    def test_the_naming_series_mints_a_ws_name(self):
        doc = self._insert(self._shift())
        self.assertTrue(
            doc.name.startswith("WS-"),
            f"Expected the WS-.#### series to name the shift, got: {doc.name}",
        )

    def test_a_shift_with_no_name_is_refused(self):
        with self.assertRaises(frappe.exceptions.MandatoryError):
            self._shift(shift_name="").insert(ignore_permissions=True)
