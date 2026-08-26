# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _vehicle_category(**overrides):
    fields = {
        "doctype": "Vehicle Category",
        "category_name": "_T-VehicleCategory " + frappe.generate_hash(length=6),
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestVehicleCategoryNaming(FrappeTestCase):
    def test_a_padded_name_is_stored_trimmed(self):
        bare = "_T-VehicleCategory " + frappe.generate_hash(length=6)
        doc = _vehicle_category(**{"category_name": "  " + bare + "  "}).insert(ignore_permissions=True)
        self.assertEqual(doc.category_name, bare)

    def test_the_trimmed_name_is_the_record_name(self):
        bare = "_T-VehicleCategory " + frappe.generate_hash(length=6)
        doc = _vehicle_category(**{"category_name": bare + "   "}).insert(ignore_permissions=True)
        self.assertEqual(doc.name, bare)

    def test_a_missing_name_is_refused(self):
        doc = _vehicle_category(**{"category_name": None})
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
