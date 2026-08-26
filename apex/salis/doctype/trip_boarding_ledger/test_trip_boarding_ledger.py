# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.ledger_index import _constraint_exists
from apex.salis.doctype.trip_boarding_ledger.trip_boarding_ledger import on_doctype_update


def _boarding_row(**overrides):
    fields = {
        "doctype": "Trip Boarding Ledger",
        "posting_date": frappe.utils.today(),
        "outcome": "Boarded",
        "confirm_source": "_T-TripBoardingLedger",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestTripBoardingLedgerImmutability(FrappeTestCase):
    def test_a_posted_row_refuses_a_second_write(self):
        doc = _boarding_row().insert(ignore_permissions=True)
        doc.outcome = "Missed"
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)

    def test_a_first_write_is_accepted(self):
        doc = _boarding_row().insert(ignore_permissions=True)
        self.assertEqual(doc.outcome, "Boarded")


class TestTripBoardingLedgerUniqueness(FrappeTestCase):
    def test_the_trip_and_employee_pair_carries_a_unique_constraint(self):
        on_doctype_update()
        self.assertTrue(
            _constraint_exists("Trip Boarding Ledger", "unique_tbl_trip_employee")
        )
