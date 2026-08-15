# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Fuel Quota per-vehicle-per-period uniqueness guard.

The vehicle is the shipped fixture rather than one minted per case. The guard under test is
keyed on (vehicle, period), so every case drops the quotas it wrote before the next one
starts — a shared record is only reusable while each test leaves it as it found it.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle"]

PLATE = "_T ABC 1001"


class TestFuelQuotaUniqueness(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": PLATE}, "name")
        self.period = "2026-05"
        self.addCleanup(self._drop_quotas)

    def _drop_quotas(self):
        """Take every quota this case wrote off the borrowed vehicle, cancelling first
        where the case submitted, so the next case meets an empty (vehicle, period) space."""
        for name in frappe.get_all("Fuel Quota", filters={"vehicle": self.vehicle}, pluck="name"):
            doc = frappe.get_doc("Fuel Quota", name)
            if doc.docstatus == 1:
                doc.cancel()
            doc.delete(ignore_permissions=True)

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
        self._quota()
        with self.assertRaises(frappe.ValidationError):
            self._quota()

    def test_different_period_is_allowed(self):
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
        for bad in (0, -1, -0.5):
            with self.assertRaises(frappe.ValidationError):
                self._draft(bad).insert(ignore_permissions=True)

    def test_positive_allocation_is_allowed(self):
        doc = self._draft(0.1).insert(ignore_permissions=True)
        self.assertTrue(doc.name)
