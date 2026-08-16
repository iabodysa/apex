# Copyright (c) 2026, afmcoltd
"""Utility Account's own contract: it needs a building and an account number, and it takes the
utility type it is given.

The building comes from ``test_records.json``, so the link is really checked, rather than a
``QA-BLDG`` name that exists on no site with ``ignore_links=True`` passed to stop Frappe noticing,
or a sixteen-line ``test_ignore`` block for masters the account does not link to.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]

BUILDING = "_Test Building"


class TestUtilityAccount(FrappeTestCase):
    def _account(self, **overrides):
        payload = {
            "doctype": "Utility Account",
            "naming_series": "UTIL-ACC-.####",
            "building": BUILDING,
            "utility_type": "Electricity",
            "account_number": "_T-ELEC-00001",
        }
        payload.update(overrides)
        return frappe.get_doc(payload)

    def test_an_account_takes_the_utility_type_it_is_given(self):
        account = self._account()
        account.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Utility Account", account.name, force=True, ignore_permissions=True
        )

        self.assertEqual(account.utility_type, "Electricity")
        self.assertEqual(account.building, BUILDING)

    def test_an_account_without_a_building_is_refused(self):
        account = self._account(building=None, utility_type="Water", account_number="_T-WAT-00001")

        with self.assertRaises(frappe.exceptions.MandatoryError):
            account.insert(ignore_permissions=True)

    def test_an_account_without_a_number_is_refused(self):
        account = self._account(utility_type="Gas", account_number=None)

        with self.assertRaises(frappe.exceptions.MandatoryError):
            account.insert(ignore_permissions=True)
