# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _scan_log(**overrides):
    fields = {
        "doctype": "Boarding Scan Log",
        "result": "Valid",
        "method": "QR",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestBoardingScanLogStamp(FrappeTestCase):
    def test_a_scan_with_no_time_is_stamped_at_insert(self):
        doc = _scan_log().insert(ignore_permissions=True)
        self.assertTrue(doc.scanned_at)

    def test_a_scan_that_carries_its_own_time_keeps_it(self):
        moment = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-3)
        doc = _scan_log(scanned_at=moment).insert(ignore_permissions=True)
        self.assertEqual(
            frappe.utils.get_datetime(doc.scanned_at), frappe.utils.get_datetime(moment)
        )


class TestBoardingScanLogAppendOnly(FrappeTestCase):
    def test_a_stored_scan_refuses_a_second_write(self):
        doc = _scan_log().insert(ignore_permissions=True)
        doc.notes = "_T-BoardingScanLog edit"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)
