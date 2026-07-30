# Copyright (c) 2026, AFMCO and contributors
"""Tests for the shared salis.utils small helpers deduped in R4.

Locks in the byte-identical behaviour of the three helpers that replaced
copy-pasted inline expressions across the Salis module:

* ``normalize_plate`` — the canonical plate key (strip whitespace + upper-case),
  formerly re-implemented in Salis Vehicle / fleet_import / fleet_os.
* ``expiry_state`` — signed days-to-expiry + near/over-expiry state, formerly the
  same ternary in the driver-portal licence countdown and vehicle-compliance list.
* ``days_until`` — defensive whole-days-until helper, formerly duplicated in
  masar.py and driver_portal/profile.py.
* ``lock_fuel_quota`` — the ``FOR UPDATE`` row lock formerly inlined twice in
  Fuel Request quota consumption/reversal.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from apex.salis.utils import days_until, expiry_state, lock_fuel_quota, normalize_plate


class TestSalisUtils(FrappeTestCase):
    # normalize_plate
    def test_normalize_plate_strips_and_uppercases(self):
        self.assertEqual(normalize_plate("abc 123"), "ABC123")
        self.assertEqual(normalize_plate("  a b c  "), "ABC")
        self.assertEqual(normalize_plate("ABC123"), "ABC123")
        # tabs / newlines are whitespace and are stripped too
        self.assertEqual(normalize_plate("a\tb\nc"), "ABC")

    def test_normalize_plate_coerces_non_str(self):
        # fleet_os wrapped the value in str(); the helper preserves that
        self.assertEqual(normalize_plate(12345), "12345")

    # expiry_state
    def _state_for_offset(self, offset_days, warn_days=30):
        expiry = add_days(getdate(), offset_days)
        return expiry_state(expiry, warn_days)

    def test_expiry_state_expired(self):
        days, state = self._state_for_offset(-1)
        self.assertEqual(days, -1)
        self.assertEqual(state, "expired")

    def test_expiry_state_expiring_at_zero(self):
        days, state = self._state_for_offset(0)
        self.assertEqual(days, 0)
        self.assertEqual(state, "expiring")

    def test_expiry_state_boundary_at_warn_days_is_expiring(self):
        # days == warn_days must be "expiring" (the ternary is <=, not <)
        days, state = self._state_for_offset(30, warn_days=30)
        self.assertEqual(days, 30)
        self.assertEqual(state, "expiring")

    def test_expiry_state_just_past_boundary_is_valid(self):
        # days == warn_days + 1 crosses into "valid"
        days, state = self._state_for_offset(31, warn_days=30)
        self.assertEqual(days, 31)
        self.assertEqual(state, "valid")

    # days_until
    def test_days_until_none_for_empty(self):
        self.assertIsNone(days_until(None))
        self.assertIsNone(days_until(""))

    def test_days_until_counts_forward(self):
        self.assertEqual(days_until(add_days(getdate(), 5)), 5)
        self.assertEqual(days_until(add_days(getdate(), -3)), -3)

    def test_days_until_none_for_unparseable(self):
        # a malformed value degrades to None rather than raising
        self.assertIsNone(days_until("not-a-date"))

    # lock_fuel_quota
    def test_lock_fuel_quota_noop_on_empty(self):
        # matches the lock_vehicle/lock_driver house style: falsy name = no-op
        try:
            lock_fuel_quota(None)
            lock_fuel_quota("")
        except Exception as exc:  # pragma: no cover
            self.fail(f"lock_fuel_quota should be a no-op on empty, raised {exc!r}")

    def test_lock_fuel_quota_issues_for_update(self):
        # Call the PRODUCTION helper and capture the SQL it actually emits; stripping
        # `.for_update()` from lock_fuel_quota must make this fail. (The old test rebuilt
        # the query inline and never touched the helper, so it stayed green even if the
        # helper lost its row lock.)
        vehicle = frappe.get_doc({
            "doctype": "Salis Vehicle",
            "plate_number": f"FQLOCK-{frappe.generate_hash(length=12)}",
            "status": "Active",
        }).insert(ignore_permissions=True).name
        self.addCleanup(
            frappe.delete_doc, "Salis Vehicle", vehicle, force=True, ignore_permissions=True
        )
        quota = frappe.get_doc({
            "doctype": "Fuel Quota",
            "vehicle": vehicle,
            "period_month": "2026-07",
            "monthly_litres": 100,
            "status": "Active",
        }).insert(ignore_permissions=True).name
        self.addCleanup(
            frappe.delete_doc, "Fuel Quota", quota, force=True, ignore_permissions=True
        )

        # frappe.qb ... .run() funnels the finished SQL string through frappe.db.sql;
        # record it around the single helper call, then restore.
        captured: list[str] = []
        real_sql = frappe.db.sql

        def _recording_sql(query, *args, **kwargs):
            captured.append(str(query))
            return real_sql(query, *args, **kwargs)

        frappe.db.sql = _recording_sql
        try:
            lock_fuel_quota(quota)
        finally:
            frappe.db.sql = real_sql

        locking = [q for q in captured if "Fuel Quota" in q and "FOR UPDATE" in q.upper()]
        self.assertTrue(
            locking,
            "lock_fuel_quota must emit a `SELECT ... FOR UPDATE` on `tabFuel Quota` "
            "(regression: for_update() stripped from the helper)",
        )

    def test_lock_fuel_quota_runs_against_db(self):
        # Executes the real FOR UPDATE SELECT (0 rows for a ghost name) without error,
        # proving the helper's query is valid SQL on the live schema.
        try:
            lock_fuel_quota(f"NO-SUCH-QUOTA-{frappe.generate_hash(length=12)}")
        except Exception as exc:  # pragma: no cover
            self.fail(f"lock_fuel_quota raised on a valid table lock: {exc!r}")


class TestRiderClearanceSparesTheCallersEarlierRows(FrappeTestCase):
	"""The docstring promises the helper "can never abort the guarded transaction".

	Only a savepoint can keep that promise: a bare rollback discards the caller's whole
	transaction, including the very rejection this follow-up task accompanies. This test
	is what makes the promise falsifiable rather than decorative.
	"""

	def setUp(self):
		frappe.set_user("Administrator")

	def test_a_failing_clearance_leaves_an_earlier_row_intact(self):
		from apex.salis.utils import raise_rider_clearance_task

		earlier = frappe.get_doc(
			{
				"doctype": "ToDo",
				"description": "row written before the clearance helper fails",
				"allocated_to": "Administrator",
			}
		).insert(ignore_permissions=True)
		self.addCleanup(
			frappe.delete_doc, "ToDo", earlier.name, force=True, ignore_permissions=True
		)

		# A driver name that resolves to no Salis Driver: assignee resolution raises
		# inside the try, which is the failure shape the except block exists for.
		self.assertEqual(
			raise_rider_clearance_task("NO-SUCH-DRIVER-FOR-CLEARANCE-PROBE"),
			[],
			"the helper swallows the failure and returns an empty list",
		)

		self.assertTrue(
			frappe.db.exists("ToDo", earlier.name),
			"the caller's earlier row was rolled back by the failing clearance helper",
		)
