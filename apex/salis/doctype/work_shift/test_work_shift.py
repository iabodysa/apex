from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWorkShift(FrappeTestCase):
    def _shift(self, *, start_time="20:00:00", end_time="05:00:00", days=None):
        return frappe.get_doc(
            {
                "doctype": "Work Shift",
                "shift_name": "Night",
                "start_time": start_time,
                "end_time": end_time,
                "applicable_days": days or [],
            }
        )

    def test_overnight_shift_is_valid_and_duplicate_days_are_removed(self):
        shift = self._shift(
            days=[
                {"day_of_week": "Monday"},
                {"day_of_week": "Monday"},
                {"day_of_week": "Tuesday"},
            ]
        )

        shift.validate()

        self.assertEqual(
            [row.day_of_week for row in shift.applicable_days],
            ["Monday", "Tuesday"],
        )

    def test_shift_requires_at_least_one_day(self):
        shift = self._shift(days=[])

        with self.assertRaises(frappe.ValidationError):
            shift.validate()

    def test_shift_rejects_equal_start_and_end_times(self):
        shift = self._shift(
            start_time="08:00:00",
            end_time="08:00:00",
            days=[{"day_of_week": "Sunday"}],
        )

        with self.assertRaises(frappe.ValidationError):
            shift.validate()


# --- merged from test_work_shift_naming.py ---
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
