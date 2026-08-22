# Copyright (c) 2026, afmcoltd
"""What a Temporary Worker guarantees, asserted against the DocType itself.

The temporary window is the whole point of this DocType: ``window_days`` defaults
and is bounded between one day and the ninety-day maximum, and ``expiry_date`` is
always derived from ``arrival_date + window_days`` rather than set by hand. Each
bound's refusal carries a sibling proving the boundary value itself is accepted.

``passport_number`` is UNIQUE and the fixture rows in ``test_records.json`` stand
for the whole run (``setUpClass`` inserts them once, and nothing rolls back between
test methods in the same class), so every test here that actually inserts gives its
copy its own passport number rather than reusing the fixture's.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

test_dependencies = []


class TestTemporaryWorker(FrappeTestCase):
    def test_window_days_defaults_to_thirty_when_unset(self):
        """An unset window must not silently become a zero-day (immediately expired) stay."""
        worker = frappe.copy_doc(frappe.get_test_records("Temporary Worker")[0])
        worker.passport_number = "_T-P9000001"
        worker.window_days = None
        worker.insert()
        self.assertEqual(worker.window_days, 30)

    def test_a_negative_window_is_refused(self):
        """A stay of negative length is not a temporary-worker window.

        Zero does NOT reach this refusal: ``_validate_window_days`` tests
        ``if not self.window_days`` first, and 0 is falsy in Python, so a
        window of 0 is silently promoted to the 30-day default rather than
        refused (pinned by ``test_a_window_of_zero_days_defaults_to_thirty``
        below) — only a genuinely negative value is truthy enough to reach
        the explicit bound check.
        """
        worker = frappe.copy_doc(frappe.get_test_records("Temporary Worker")[0])
        worker.window_days = -1
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Window Days must be at least 1 day",
            worker.insert,
        )

    def test_a_window_of_zero_days_defaults_to_thirty(self):
        """0 is falsy, so it takes the same silent-default path as an unset window."""
        worker = frappe.copy_doc(frappe.get_test_records("Temporary Worker")[0])
        worker.passport_number = "_T-P9000005"
        worker.window_days = 0
        worker.insert()
        self.assertEqual(worker.window_days, 30)

    def test_a_window_of_exactly_one_day_is_accepted(self):
        """One day is the narrowest window the controller allows."""
        worker = frappe.copy_doc(frappe.get_test_records("Temporary Worker")[0])
        worker.passport_number = "_T-P9000002"
        worker.arrival_date = nowdate()
        worker.window_days = 1
        worker.insert()
        self.assertEqual(worker.window_days, 1)
        self.assertEqual(worker.expiry_date, add_days(nowdate(), 1))

    def test_a_window_over_ninety_days_is_refused(self):
        """Past ninety days this is no longer a temporary arrangement, and the server says so."""
        worker = frappe.copy_doc(frappe.get_test_records("Temporary Worker")[0])
        worker.window_days = 91
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Window Days cannot exceed 90 days",
            worker.insert,
        )

    def test_a_window_of_exactly_ninety_days_is_accepted(self):
        """Ninety days is the widest window the controller allows."""
        worker = frappe.copy_doc(frappe.get_test_records("Temporary Worker")[0])
        worker.passport_number = "_T-P9000003"
        worker.arrival_date = nowdate()
        worker.window_days = 90
        worker.insert()
        self.assertEqual(worker.window_days, 90)
        self.assertEqual(worker.expiry_date, add_days(nowdate(), 90))

    def test_expiry_date_is_derived_from_arrival_date_plus_window_days(self):
        """A hand-set expiry date must not survive save; it is always recomputed here."""
        worker = frappe.copy_doc(frappe.get_test_records("Temporary Worker")[0])
        worker.passport_number = "_T-P9000004"
        worker.arrival_date = nowdate()
        worker.window_days = 45
        worker.insert()
        self.assertEqual(worker.expiry_date, add_days(nowdate(), 45))
