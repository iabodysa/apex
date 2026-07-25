# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for apex_core.utils.addresses display helpers.

The Address DB read (and the native ``get_default_address`` resolver) are
mocked, so the ordered comma-join of non-empty parts and the empty-input guards
are exercised without a live site.
"""

from __future__ import annotations

import unittest
from unittest import mock

from apex.apex_core.utils import addresses

_ROW = {
    "address_line1": "123 King Fahd Rd",
    "address_line2": "",
    "city": "Riyadh",
    "state": "",
    "pincode": "",
    "country": "Saudi Arabia",
}


class TestAddressText(unittest.TestCase):
    def test_by_name_joins_non_empty_parts_in_order(self):
        with mock.patch.object(addresses, "frappe") as mf:
            mf.db.get_value.return_value = dict(_ROW)
            self.assertEqual(
                addresses.get_address_text_by_name("ADDR-1"),
                "123 King Fahd Rd, Riyadh, Saudi Arabia",
            )

    def test_by_name_none_short_circuits_without_a_db_read(self):
        with mock.patch.object(addresses, "frappe") as mf:
            self.assertEqual(addresses.get_address_text_by_name(None), "")
            mf.db.get_value.assert_not_called()

    def test_by_name_missing_address_returns_empty(self):
        with mock.patch.object(addresses, "frappe") as mf:
            mf.db.get_value.return_value = None
            self.assertEqual(addresses.get_address_text_by_name("ADDR-X"), "")

    def test_get_address_text_none_name_returns_empty(self):
        with mock.patch.object(addresses, "frappe"):
            self.assertEqual(addresses.get_address_text("Company", None), "")

    def test_get_address_text_resolves_default_then_joins(self):
        with mock.patch.object(addresses, "frappe") as mf, mock.patch(
            "frappe.contacts.doctype.address.address.get_default_address",
            return_value="ADDR-1",
        ):
            mf.db.get_value.return_value = dict(_ROW)
            self.assertEqual(
                addresses.get_address_text("Company", "Acme"),
                "123 King Fahd Rd, Riyadh, Saudi Arabia",
            )


if __name__ == "__main__":
    unittest.main()
