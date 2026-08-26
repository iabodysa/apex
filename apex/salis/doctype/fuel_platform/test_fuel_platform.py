# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _fuel_platform(**overrides):
    fields = {
        "doctype": "Fuel Platform",
        "platform_name": "_T-FuelPlatform " + frappe.generate_hash(length=6),
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestFuelPlatformNaming(FrappeTestCase):
    def test_a_padded_name_is_stored_trimmed(self):
        bare = "_T-FuelPlatform " + frappe.generate_hash(length=6)
        doc = _fuel_platform(**{"platform_name": "  " + bare + "  "}).insert(ignore_permissions=True)
        self.assertEqual(doc.platform_name, bare)

    def test_the_trimmed_name_is_the_record_name(self):
        bare = "_T-FuelPlatform " + frappe.generate_hash(length=6)
        doc = _fuel_platform(**{"platform_name": bare + "   "}).insert(ignore_permissions=True)
        self.assertEqual(doc.name, bare)

    def test_a_missing_name_is_refused(self):
        doc = _fuel_platform(**{"platform_name": None})
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
