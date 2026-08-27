# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.material_transfer.material_transfer import validate


class TestMaterialTransferValidate(FrappeTestCase):
    def _doc(self, **fields):
        doc = frappe.new_doc("Material Transfer")
        doc.update(fields)
        return doc

    def test_a_transfer_with_no_items_is_refused(self):
        doc = self._doc(
            transfer_date=frappe.utils.today(),
            from_building="_Test Building",
            to_building="_Test Building 2",
        )
        with self.assertRaises(frappe.MandatoryError):
            doc.insert()

    def test_the_same_building_on_both_sides_is_refused(self):
        doc = self._doc(from_building="_Test Building", to_building="_Test Building")
        doc.append("items", {"qty": 1})
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_a_non_positive_quantity_is_refused(self):
        doc = self._doc(from_building="_Test Building", to_building="_Test Building 2")
        doc.append("items", {"qty": 0})
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_different_buildings_and_a_positive_qty_pass(self):
        doc = self._doc(from_building="_Test Building", to_building="_Test Building 2")
        doc.append("items", {"qty": 1})
        validate(doc)
