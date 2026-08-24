# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestOperationalDepreciationPolicyGuards(FrappeTestCase):
    def _policy(self, **fields):
        data = {
            "doctype": "Operational Depreciation Policy",
            "policy_name": "_T-ODP Guard",
            "useful_life_years": 5,
            "depreciation_method": "Straight Line",
            "residual_value_pct": 10,
        }
        data.update(fields)
        return frappe.get_doc(data)

    def test_a_zero_useful_life_is_refused(self):
        doc = self._policy(policy_name="_T-ODP Zero Life", useful_life_years=0)
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_a_residual_value_percent_above_100_is_refused(self):
        doc = self._policy(policy_name="_T-ODP Over Residual", residual_value_pct=101)
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
