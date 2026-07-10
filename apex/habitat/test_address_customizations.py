# Copyright (c) 2026, AFMCO and contributors
"""Saudi National Address validation on the native Address DocType.

The custom fields (short_address / building_number / secondary_number / district)
are added via habitat/custom/address.json; the validate hook
(habitat.address_customizations.validate) enforces the SPL formats. These tests
pin that contract: a valid Short Address is accepted and upper-cased; malformed
Short / Building / Secondary numbers are rejected."""

import frappe
from frappe.tests.utils import FrappeTestCase


def _h(n=6):
    return frappe.generate_hash(length=n).upper()


class TestAddressCustomizations(FrappeTestCase):
    def _address(self, **extra):
        doc = frappe.get_doc({
            "doctype": "Address",
            "address_title": "ADDR-" + _h(),
            "address_type": "Office",
            "address_line1": "Test line",
            "city": "Riyadh",
            "country": "Saudi Arabia",
            **extra,
        })
        doc.insert(ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Address", doc.name, force=True, ignore_permissions=True)
        return doc

    def test_valid_short_address_is_accepted_and_uppercased(self):
        doc = self._address(short_address="rctb4359", building_number="2929", secondary_number="1234")
        self.assertEqual(doc.short_address, "RCTB4359")
        self.assertEqual(doc.building_number, "2929")
        self.assertEqual(doc.secondary_number, "1234")

    def test_blank_saudi_fields_are_allowed(self):
        # The fields are optional — a plain address must still save.
        doc = self._address()
        self.assertFalse(doc.get("short_address"))

    def test_malformed_short_address_is_rejected(self):
        for bad in ("RCT4359", "RCTBB359", "RCTB435", "RCTB43590", "1234ABCD"):
            with self.assertRaises(frappe.ValidationError):
                self._address(short_address=bad)

    def test_non_four_digit_building_number_is_rejected(self):
        for bad in ("29", "292929", "29A9"):
            with self.assertRaises(frappe.ValidationError):
                self._address(building_number=bad)

    def test_non_four_digit_secondary_number_is_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            self._address(secondary_number="12")
