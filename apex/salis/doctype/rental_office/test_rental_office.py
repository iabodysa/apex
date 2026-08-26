# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _rental_office(**overrides):
    fields = {
        "doctype": "Rental Office",
        "office_name": "_T-RentalOffice " + frappe.generate_hash(length=6),
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestRentalOfficeNaming(FrappeTestCase):
    def test_a_padded_name_is_stored_trimmed(self):
        bare = "_T-RentalOffice " + frappe.generate_hash(length=6)
        doc = _rental_office(**{"office_name": "  " + bare + "  "}).insert(ignore_permissions=True)
        self.assertEqual(doc.office_name, bare)

    def test_the_trimmed_name_is_the_record_name(self):
        bare = "_T-RentalOffice " + frappe.generate_hash(length=6)
        doc = _rental_office(**{"office_name": bare + "   "}).insert(ignore_permissions=True)
        self.assertEqual(doc.name, bare)

    def test_a_missing_name_is_refused(self):
        doc = _rental_office(**{"office_name": None})
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
