# Copyright (c) 2026, afmcoltd
"""What a Trip Fulfilment Ledger guarantees, asserted against the DocType itself.

A posted row is immutable: any save of an already-persisted row is refused,
only the initial insert is allowed through. One completion memo per trip is a
real DB-level backstop: ``on_doctype_update``'s UNIQUE index on
``dispatch_trip`` alone (``unique_tfl_trip``) — a single non-nullable-in-
practice column, unlike the composite ``(..., reversal_of)`` keys elsewhere in
this module, so this one is not exposed to the NULL-never-equals-NULL gap
those carry (see the Rental Accrual Ledger and Trip Boarding Ledger tests).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle", "Salis Driver"]


class TestTripFulfilmentLedger(FrappeTestCase):
    def test_editing_a_posted_row_is_refused(self):
        """A posted completion memo is an audit record; it must never be silently rewritten."""
        ledger = frappe.copy_doc(frappe.get_test_records("Trip Fulfilment Ledger")[0])
        ledger.insert()
        ledger.worker_count = 99
        self.assertRaisesRegex(
            frappe.PermissionError,
            "cannot be edited",
            ledger.save,
        )

    def test_a_second_completion_memo_for_the_same_trip_is_refused(self):
        """A second post for one trip would double-count it in the fulfilment-rate KPI."""
        trip = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "trip_type": "Ad Hoc",
                "trip_date": frappe.utils.nowdate(),
            }
        ).insert()

        first = frappe.copy_doc(frappe.get_test_records("Trip Fulfilment Ledger")[0])
        first.dispatch_trip = trip.name
        first.insert()

        duplicate = frappe.copy_doc(frappe.get_test_records("Trip Fulfilment Ledger")[0])
        duplicate.dispatch_trip = trip.name
        self.assertRaisesRegex(
            frappe.UniqueValidationError,
            "unique_tfl_trip",
            duplicate.insert,
        )
