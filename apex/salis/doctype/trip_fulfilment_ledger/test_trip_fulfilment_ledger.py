# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.ledger_index import _constraint_exists
from apex.salis.doctype.trip_fulfilment_ledger.trip_fulfilment_ledger import on_doctype_update


def _fulfilment_row(**overrides):
    fields = {
        "doctype": "Trip Fulfilment Ledger",
        "trip_date": frappe.utils.today(),
        "worker_count": 4,
        "source_doctype": "_T-TripFulfilmentLedger",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestTripFulfilmentLedgerImmutability(FrappeTestCase):
    def test_a_posted_row_refuses_a_second_write(self):
        doc = _fulfilment_row().insert(ignore_permissions=True)
        doc.worker_count = 9
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)

    def test_a_first_write_is_accepted(self):
        doc = _fulfilment_row().insert(ignore_permissions=True)
        self.assertEqual(doc.worker_count, 4)


class TestTripFulfilmentLedgerUniqueness(FrappeTestCase):
    def test_one_dispatch_trip_carries_a_unique_constraint(self):
        on_doctype_update()
        self.assertTrue(_constraint_exists("Trip Fulfilment Ledger", "unique_tfl_trip"))
