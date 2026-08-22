# Copyright (c) 2026, afmcoltd
"""What a Fuel Quota guarantees, asserted against the DocType itself.

One live quota per vehicle per period: a second (vehicle, period_month) row
while the first is still live (docstatus < 2) would double-allocate the same
month. ``monthly_litres`` must be positive. A quota whose consumption already
exceeds its allocation is flagged with a warning, not blocked — Fuel Request
is what actually gates further draws against an exhausted quota.

``test_records.json``'s row 0 (vehicle VEH-000001, period 2026-01) is already
standing before any test method runs, so it is the duplicate-refusal test's
negative control.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle"]


class TestFuelQuota(FrappeTestCase):
    def test_a_duplicate_live_quota_for_the_same_vehicle_and_period_is_refused(self):
        """A second allocation for the same vehicle and month would double-allocate it."""
        duplicate = frappe.copy_doc(frappe.get_test_records("Fuel Quota")[0])
        self.assertRaisesRegex(
            frappe.ValidationError,
            "already exists for vehicle",
            duplicate.insert,
        )

    def test_a_zero_or_negative_monthly_litres_is_refused(self):
        """An allocation of zero or less litres is not an allocation."""
        quota = frappe.copy_doc(frappe.get_test_records("Fuel Quota")[0])
        quota.period_month = "2026-03"
        quota.monthly_litres = 0
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Monthly litres must be greater than zero",
            quota.insert,
        )

    def test_consumption_over_the_allocation_warns_but_does_not_block_saving(self):
        """Over-consumption is a signal for review, not a hard stop this controller owns."""
        quota = frappe.copy_doc(frappe.get_test_records("Fuel Quota")[0])
        quota.period_month = "2026-04"
        quota.monthly_litres = 100
        quota.consumed_litres = 150
        frappe.clear_messages()
        quota.insert()
        self.assertTrue(quota.name)
        self.assertTrue(
            any("exceed the monthly quota" in (m.get("message") or "") for m in frappe.message_log)
        )
