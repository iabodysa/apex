# Copyright (c) 2026, AFMCO and contributors
"""The Arrivals Desk must learn its one feature flag without reading Habitat Settings.

The page asked ``frappe.client.get_single_value`` for
``Habitat Settings.enable_passport_mrz_ocr`` on every load. Habitat Settings carries a
single DocPerm row (System Manager), so the Resident Supervisor the page is published
to hit a blocking permission dialog before the desk had rendered anything — a JS
``.catch()`` cannot suppress that dialog, because ``frappe.request`` raises it from the
transport layer, not from the promise the caller holds.

Widening Habitat Settings would have handed the same role the company, the finance and
safety notification addresses, the supplier markup and the handover OTP window to reach
one boolean. These cases pin the narrow route instead: an accessor that answers only
that flag, only to a caller who could actually use the passport sheet it gates, and
answers "off" rather than refusing to everyone else — so the desk always loads.

Run standalone:
  bench --site <site> run-tests --module apex.habitat.api.test_arrivals_desk_intake_settings
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api import arrivals_desk
from apex.tests._helpers import _user, as_user

FLAG = "enable_passport_mrz_ocr"


class TestArrivalsDeskIntakeSettings(FrappeTestCase):
    """A Single is not rolled back by the per-test transaction, so its value is
    captured and restored through addCleanup BEFORE any case mutates it."""

    def setUp(self):
        frappe.set_user("Administrator")
        original = frappe.db.get_single_value("Habitat Settings", FLAG)
        self.addCleanup(
            frappe.db.set_single_value, "Habitat Settings", FLAG, original
        )
        self.addCleanup(frappe.set_user, "Administrator")
        self.supervisor = _user("ads_res_sup@example.com", "Resident Supervisor")

    def _set_flag(self, value):
        frappe.db.set_single_value("Habitat Settings", FLAG, value)

    # [#7ffkxk]

    def test_the_pages_audience_cannot_read_the_single(self):
        """PREMISE. If this ever goes false the accessor is no longer needed — but it
        must be proven, not assumed, or the cases below prove nothing."""
        with as_user(self.supervisor):
            self.assertFalse(
                frappe.has_permission("Habitat Settings", "read"),
                "Habitat Settings was widened; re-decide whether the accessor is still "
                "the narrower route",
            )

    def test_supervisor_gets_the_flag_without_reading_the_single(self):
        self._set_flag(1)
        with as_user(self.supervisor):
            flags = arrivals_desk.get_intake_settings()
        self.assertTrue(flags[FLAG])

    def test_the_answer_tracks_the_setting(self):
        """NEGATIVE CONTROL. An accessor hardcoded to either constant passes exactly
        one of these two; both together force it to read the Single."""
        self._set_flag(0)
        with as_user(self.supervisor):
            self.assertFalse(arrivals_desk.get_intake_settings()[FLAG])
        self._set_flag(1)
        with as_user(self.supervisor):
            self.assertTrue(arrivals_desk.get_intake_settings()[FLAG])

    def test_a_caller_who_cannot_register_arrivals_is_told_off_not_refused(self):
        """The flag gates the passport register sheet, which needs Temporary Worker
        create. A caller without it gets ``False`` — never an exception, because a
        raised permission error is exactly the blocking dialog this replaces."""
        self._set_flag(1)
        outsider = _user("ads_outsider@example.com", "Blogger")
        with as_user(outsider):
            self.assertFalse(frappe.has_permission("Temporary Worker", "create"))
            self.assertFalse(arrivals_desk.get_intake_settings()[FLAG])

    def test_the_accessor_never_returns_another_setting(self):
        """The point of the accessor is that it is not a window onto the Single."""
        with as_user(self.supervisor):
            flags = arrivals_desk.get_intake_settings()
        self.assertEqual(set(flags), {FLAG})


if __name__ == "__main__":
    unittest.main()
