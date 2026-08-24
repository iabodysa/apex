# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today


def _temporary_worker(**overrides):
    fields = {
        "doctype": "Temporary Worker",
        "worker_name": "_T-Temp Worker Validate",
        "passport_number": frappe.generate_hash(length=10),
        "arrival_date": today(),
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestTemporaryWorkerWindowDays(FrappeTestCase):
    def test_a_negative_window_is_refused(self):
        doc = _temporary_worker(window_days=-5)
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_a_window_beyond_ninety_days_is_refused(self):
        doc = _temporary_worker(window_days=91)
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_an_explicit_zero_window_is_reset_to_thirty_days(self):
        doc = _temporary_worker(window_days=0).insert(ignore_permissions=True)
        self.assertEqual(doc.window_days, 30)


class TestTemporaryWorkerExpiryDate(FrappeTestCase):
    def test_expiry_date_is_arrival_date_plus_window_days(self):
        doc = _temporary_worker(
            arrival_date=today(), window_days=45
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.expiry_date, add_days(today(), 45))
