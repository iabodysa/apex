# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]


class TestGoodsReceiptValidate(FrappeTestCase):
    def _doc(self, **fields):
        doc = frappe.new_doc("Goods Receipt")
        doc.update(fields)
        return doc

    def test_a_non_procurement_building_is_refused(self):
        doc = self._doc(intake_building="_Test Building")
        with self.assertRaises(frappe.ValidationError):
            doc.validate()

    def test_a_flagged_procurement_store_passes_the_gate(self):
        doc = self._doc(intake_building="_Test Building 2")
        doc.append("items", {"qty": 1})
        doc.validate()

    def test_a_non_positive_quantity_is_refused_even_on_a_valid_store(self):
        doc = self._doc(intake_building="_Test Building 2")
        doc.append("items", {"qty": 0})
        with self.assertRaises(frappe.ValidationError):
            doc.validate()
