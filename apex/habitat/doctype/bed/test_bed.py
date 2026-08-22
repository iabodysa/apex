# Copyright (c) 2026, afmcoltd
"""Bed's own contract: it needs a room and a code, and it takes the code it is given.

The Room comes from its ``test_records.json``, which pulls the Building along with it, so nothing
here builds either. The old form of this file hard-coded ``ROOM-0001`` and passed
``ignore_links=True``, which meant the link was never really checked.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Room"]

class TestBed(FrappeTestCase):
    def test_a_bed_takes_the_code_it_is_given(self):
        bed = frappe.get_doc({
            "doctype": "Bed",
            "naming_series": "BED-.####",
            "room": "_T-101",
            "bed_code": "_T-BED-A1",
        })
        bed.insert(ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Bed", bed.name, force=True, ignore_permissions=True)

        self.assertEqual(bed.bed_code, "_T-BED-A1")
        self.assertEqual(bed.room, "_T-101")

    def test_a_bed_without_a_room_is_refused(self):
        bed = frappe.get_doc({
            "doctype": "Bed",
            "naming_series": "BED-.####",
            "bed_code": "_T-BED-X9",
        })

        with self.assertRaises(frappe.exceptions.MandatoryError):
            bed.insert(ignore_permissions=True)

    def test_a_bed_without_a_code_is_refused(self):
        bed = frappe.get_doc({
            "doctype": "Bed",
            "naming_series": "BED-.####",
            "room": "_T-101",
        })

        with self.assertRaises(frappe.exceptions.ValidationError):
            bed.insert(ignore_permissions=True)
