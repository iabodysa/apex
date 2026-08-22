# Copyright (c) 2026, afmcoltd
"""What Lease guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is the module-level
``validate`` wired in ``hooks.py``. It refuses a term that ends on or before it starts, a
first payment date before the lease starts, a utility cost share outside 0-100, and a
lease whose dates overlap another lease already standing on the same building. On a
clean insert it also builds the payment schedule from ``first_payment_date`` and
``billing_cycle``, run fresh from the original anchor each time so a mid-year lease
never drifts onto a clamped short-month day. The workflow that carries this DocType to
Approved/Active is Finance-Manager-gated and out of scope for a single validate test.

Every case builds on a throwaway Building of its own rather than the shared
``_Test Building`` fixture row: the overlap guard is scoped by building, and this
DocType's own test class shares one transaction across its methods (`FrappeTestCase`
rolls back once at class teardown, not per test), so two cases sharing a building
would see each other's leases.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

test_dependencies = ["Building"]


def _fresh_building():
    """A Building unique to the calling test, so its lease never collides with one
    already standing (in this run or left over from another) on a shared fixture building."""
    building = frappe.copy_doc(frappe.get_test_records("Building")[0])
    building.building_name = f"_T-Lease Building {frappe.generate_hash(length=8)}"
    building.floor_plan = []
    building.insert()
    return building.name


class TestLease(FrappeTestCase):
    def test_a_lease_with_a_valid_term_is_accepted_and_builds_its_monthly_schedule(self):
        """The acceptance case: a normal lease inserts and its schedule is built from the anchor."""
        record = frappe.copy_doc(frappe.get_test_records("Lease")[0])
        record.building = _fresh_building()
        record.insert()

        self.assertEqual(len(record.payment_schedule), 12)
        self.assertEqual(record.total_scheduled, 60000)
        self.assertEqual(record.payment_schedule[0].due_date, getdate("2026-01-01"))
        self.assertEqual(record.payment_schedule[0].amount, 5000)
        self.assertEqual(record.payment_schedule[0].status, "Unpaid")

    def test_an_end_date_not_after_the_start_date_is_refused(self):
        """A lease term that ends on or before it starts covers no time at all."""
        record = frappe.copy_doc(frappe.get_test_records("Lease")[0])
        record.building = _fresh_building()
        record.lease_end_date = record.lease_start_date

        with self.assertRaisesRegex(frappe.ValidationError, "must be after"):
            record.insert()

    def test_a_first_payment_before_the_lease_start_is_refused(self):
        """A first payment cannot fall before the lease it pays for has begun."""
        record = frappe.copy_doc(frappe.get_test_records("Lease")[0])
        record.building = _fresh_building()
        record.first_payment_date = add_days(record.lease_start_date, -1)

        with self.assertRaisesRegex(frappe.ValidationError, "cannot be before"):
            record.insert()

    def test_a_utility_cost_share_outside_zero_to_a_hundred_is_refused(self):
        """A share above 100% or below 0% cannot be split with a landlord."""
        record = frappe.copy_doc(frappe.get_test_records("Lease")[0])
        record.building = _fresh_building()
        record.company_share_pct = 150

        with self.assertRaisesRegex(frappe.ValidationError, "between 0 and 100"):
            record.insert()

    def test_an_overlapping_lease_on_the_same_building_is_refused(self):
        """Two leases cannot both claim rent for the same building on overlapping days."""
        building = _fresh_building()

        first = frappe.copy_doc(frappe.get_test_records("Lease")[0])
        first.building = building
        first.insert()

        second = frappe.copy_doc(frappe.get_test_records("Lease")[0])
        second.building = building
        with self.assertRaisesRegex(frappe.ValidationError, "overlapping lease"):
            second.insert()

    def test_an_overlapping_term_on_a_different_building_is_accepted(self):
        """The overlap guard is scoped to one building, not the calendar in general."""
        first = frappe.copy_doc(frappe.get_test_records("Lease")[0])
        first.building = _fresh_building()
        first.insert()

        second = frappe.copy_doc(frappe.get_test_records("Lease")[0])
        second.building = _fresh_building()
        second.lease_start_date = first.lease_start_date
        second.lease_end_date = first.lease_end_date
        second.first_payment_date = first.lease_start_date
        second.insert()

        self.assertNotEqual(first.building, second.building)
