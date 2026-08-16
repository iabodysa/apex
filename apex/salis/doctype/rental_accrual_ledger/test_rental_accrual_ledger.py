# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Rental Accrual Ledger reversal path.

When a Receipt Rental Vehicle Movement is cancelled, the daily accrual rows it
produced must be netted out of the Rental Accrual Ledger by a negative mirror row
whose ``reversal_of`` points at the original — the same idiom
``fuel_engine.reverse_fuel_ledger`` uses for the Fuel Consumption Ledger. These
tests prove: cancelling the Receipt posts the reversal, the source nets to zero,
and the reversal is idempotent.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today

from apex.salis.rental_engine import daily_rental_accrual, reverse_rental_accrual

LEDGER = "Rental Accrual Ledger"


class TestRentalAccrualLedgerReversal(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.office = (
            frappe.get_doc(
                {
                    "doctype": "Rental Office",
                    "office_name": f"Office {frappe.generate_hash(length=12)}",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        self.vehicle = (
            frappe.get_doc(
                {
                    "doctype": "Salis Vehicle",
                    "plate_number": f"RA {frappe.generate_hash(length=12)}",
                    "status": "Active",
                    "ownership": "Rented",
                    "rental_office": self.office,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        self.receipt = frappe.get_doc(
            {
                "doctype": "Rental Vehicle Movement",
                "movement_type": "Receipt",
                "vehicle": self.vehicle,
                "rental_office": self.office,
                "movement_date": today(),
                "daily_rate": 75,
            }
        ).insert(ignore_permissions=True)
        self.receipt.submit()
        daily_rental_accrual()

    def _rows_for_source(self):
        return frappe.get_all(
            LEDGER,
            filters={"source_doctype": "Rental Vehicle Movement", "source_name": self.receipt.name},
            fields=["name", "amount", "reversal_of"],
        )

    def test_cancelling_the_receipt_reverses_its_accrual(self):
        originals = self._rows_for_source()
        self.assertEqual(len(originals), 1, "The daily accrual job must have posted one row.")

        self.receipt.cancel()

        reversal = frappe.get_all(
            LEDGER, filters={"reversal_of": originals[0].name}, fields=["amount", "vehicle"]
        )
        self.assertEqual(len(reversal), 1, "Cancelling the Receipt must post one reversal row.")
        self.assertEqual(flt(reversal[0].amount), -flt(originals[0].amount))
        self.assertEqual(reversal[0].vehicle, self.vehicle)

        net = flt(sum(flt(r.amount) for r in self._rows_for_source())) + flt(
            sum(flt(r.amount) for r in reversal)
        )
        self.assertEqual(net, 0.0)

    def test_reversal_is_idempotent(self):
        self.receipt.cancel()
        again = reverse_rental_accrual("Rental Vehicle Movement", self.receipt.name)
        self.assertEqual(again, 0, "A source already fully reversed must not be reversed twice.")

    def test_unaccrued_source_is_noop(self):
        posted = reverse_rental_accrual("Rental Vehicle Movement", "NEVER ACCRUED XYZ")
        self.assertEqual(posted, 0)
