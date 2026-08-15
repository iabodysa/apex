# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Fuel Exception Case amount-recovered guard.

The negative-amount guard runs unconditionally in validate(), before the
status-dependent closure controls, so it is exercised here on a plain Open
draft in isolation from the evidence/non-raiser-closer requirements.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_ignore = ["Payment Gateway"]


class TestFuelExceptionCaseAmount(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def _case(self, amount):
        return frappe.get_doc(
            {
                "doctype": "Fuel Exception Case",
                "exception_type": "Over-Consumption",
                "description": "Test case",
                "status": "Open",
                "amount_recovered": amount,
            }
        )

    def test_negative_amount_recovered_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            self._case(-1).insert(ignore_permissions=True)

    def test_zero_or_positive_amount_recovered_allowed(self):
        zero = self._case(0).insert(ignore_permissions=True)
        self.assertTrue(zero.name)
        positive = self._case(500).insert(ignore_permissions=True)
        self.assertTrue(positive.name)
