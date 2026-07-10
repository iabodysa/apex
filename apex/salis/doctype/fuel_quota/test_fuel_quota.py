# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Fuel Quota per-vehicle-per-period uniqueness guard."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestFuelQuotaUniqueness(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.vehicle = (
            frappe.get_doc(
                {
                    "doctype": "Salis Vehicle",
                    "plate_number": f"FQ {frappe.generate_hash(length=12)}",
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        self.period = "2026-05"

    def _quota(self, period=None):
        return frappe.get_doc(
            {
                "doctype": "Fuel Quota",
                "vehicle": self.vehicle,
                "period_month": period or self.period,
                "monthly_litres": 100,
            }
        ).insert(ignore_permissions=True)

    def test_duplicate_vehicle_period_is_rejected(self):
        # First quota is fine; a second for the same vehicle + period double-allocates.
        self._quota()
        with self.assertRaises(frappe.ValidationError):
            self._quota()

    def test_different_period_is_allowed(self):
        # Non-vacuous: the guard is scoped to the period, not the vehicle.
        self._quota("2026-05")
        other = self._quota("2026-06")
        self.assertTrue(other.name)

    def test_reissue_after_cancel_is_allowed(self):
        """A cancelled quota must be re-issuable for the same vehicle + period.
        Both the app guard (docstatus < 2) and the DB unique index carry docstatus,
        so a Cancelled(2) row coexists with a fresh one — a bare two-column index
        would wrongly raise DuplicateEntryError here."""
        first = self._quota()
        first.submit()
        first.cancel()
        reissued = self._quota()
        self.assertTrue(reissued.name)
        self.assertNotEqual(reissued.name, first.name)

    def test_guard_locks_vehicle_before_exists_check(self):
        """The duplicate guard must FOR-UPDATE lock the vehicle row BEFORE
        the exists-check. Two concurrent creates serialize on that row lock, so the
        loser sees the winner's row and is rejected -> exactly one live quota. We
        assert the call order (lock precedes exists) since the test DB is not a
        real concurrency harness; the second sequential create still raises."""
        order = []
        real_exists = frappe.db.exists

        def track_exists(*args, **kwargs):
            order.append("exists")
            return real_exists(*args, **kwargs)

        with patch(
            "apex.salis.doctype.fuel_quota.fuel_quota.lock_vehicle",
            side_effect=lambda name: order.append("lock"),
        ), patch.object(frappe.db, "exists", side_effect=track_exists):
            self._quota()

        # lock_vehicle ran, and it ran before the first exists-check in the guard.
        self.assertIn("lock", order)
        self.assertIn("exists", order)
        self.assertLess(
            order.index("lock"),
            order.index("exists"),
            "the vehicle must be locked before the duplicate exists-check",
        )

    def test_concurrent_creates_yield_one_live_quota(self):
        """Outcome: a second create for the same (vehicle, period) is rejected
        and only one live quota survives (the serialized loser raises)."""
        self._quota()
        with self.assertRaises(frappe.ValidationError):
            self._quota()
        live = frappe.get_all(
            "Fuel Quota",
            filters={
                "vehicle": self.vehicle,
                "period_month": self.period,
                "docstatus": ["<", 2],
            },
            pluck="name",
        )
        self.assertEqual(len(live), 1, "exactly one live quota must survive")

    def _draft(self, litres):
        return frappe.get_doc(
            {
                "doctype": "Fuel Quota",
                "vehicle": self.vehicle,
                "period_month": self.period,
                "monthly_litres": litres,
            }
        )

    def test_nonpositive_allocation_is_rejected(self):
        # Zero or negative litres is not a quota; the guard rejects the whole range.
        for bad in (0, -1, -0.5):
            with self.assertRaises(frappe.ValidationError):
                self._draft(bad).insert(ignore_permissions=True)

    def test_positive_allocation_is_allowed(self):
        # Non-vacuous: the smallest positive allocation passes the same guard.
        doc = self._draft(0.1).insert(ignore_permissions=True)
        self.assertTrue(doc.name)
