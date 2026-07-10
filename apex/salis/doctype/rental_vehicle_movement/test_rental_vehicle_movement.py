# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Rental Vehicle Movement Receipt/Return lifecycle guard."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today


class TestRentalMovementLifecycle(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.office = self._office()
        self.vehicle = (
            frappe.get_doc(
                {
                    "doctype": "Salis Vehicle",
                    "plate_number": f"RV {frappe.generate_hash(length=12)}",
                    "status": "Active",
                    "ownership": "Rented",
                    "rental_office": self.office,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _office(self):
        return (
            frappe.get_doc(
                {
                    "doctype": "Rental Office",
                    "office_name": f"Office {frappe.generate_hash(length=12)}",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _movement(self, movement_type, submit=True, daily_rate=50, movement_date=None):
        doc = frappe.get_doc(
            {
                "doctype": "Rental Vehicle Movement",
                "movement_type": movement_type,
                "vehicle": self.vehicle,
                "rental_office": self.office,
                "movement_date": movement_date or today(),
                "daily_rate": daily_rate if movement_type == "Receipt" else None,
            }
        ).insert(ignore_permissions=True)
        if submit:
            doc.submit()
        return doc

    def test_return_without_open_receipt_is_rejected(self):
        # No prior Receipt -> nothing to return; would corrupt the in-service window.
        with self.assertRaises(frappe.ValidationError):
            self._movement("Return")

    def test_second_open_receipt_is_rejected(self):
        # One Receipt opens the window; a second Receipt while open is rejected.
        self._movement("Receipt")
        with self.assertRaises(frappe.ValidationError):
            self._movement("Receipt", submit=False)

    def test_return_dated_before_open_receipt_is_rejected(self):
        # T-710: Receipt opens on day 0; a Return dated the day before would invert
        # the in-service window and corrupt the accrual span -> rejected.
        self._movement("Receipt", movement_date=today())
        with self.assertRaises(frappe.ValidationError):
            self._movement("Return", movement_date=add_days(today(), -1))

    def test_return_same_day_as_receipt_is_allowed(self):
        # Boundary: a same-day Return closes a zero-length window and is allowed.
        receipt_date = add_days(today(), -2)
        self._movement("Receipt", movement_date=receipt_date)
        ret = self._movement("Return", movement_date=receipt_date)
        self.assertEqual(ret.docstatus, 1)

    def test_receipt_then_return_is_allowed(self):
        # Non-vacuous: the normal Receipt -> Return cycle passes, and a new Receipt
        # is then allowed once the window is closed.
        self._movement("Receipt")
        self._movement("Return")
        again = self._movement("Receipt")
        self.assertEqual(again.docstatus, 1)
