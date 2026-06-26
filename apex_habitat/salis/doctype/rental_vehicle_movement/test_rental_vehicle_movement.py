"""Tests for the Rental Vehicle Movement Receipt/Return lifecycle guard."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today


class TestRentalMovementLifecycle(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.office = self._office()
        self.vehicle = (
            frappe.get_doc(
                {
                    "doctype": "Salis Vehicle",
                    "plate_number": f"RV {frappe.generate_hash(length=6)}",
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
                    "office_name": f"Office {frappe.generate_hash(length=6)}",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _movement(self, movement_type, submit=True, daily_rate=50):
        doc = frappe.get_doc(
            {
                "doctype": "Rental Vehicle Movement",
                "movement_type": movement_type,
                "vehicle": self.vehicle,
                "rental_office": self.office,
                "movement_date": today(),
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

    def test_receipt_then_return_is_allowed(self):
        # Non-vacuous: the normal Receipt -> Return cycle passes, and a new Receipt
        # is then allowed once the window is closed.
        self._movement("Receipt")
        self._movement("Return")
        again = self._movement("Receipt")
        self.assertEqual(again.docstatus, 1)
