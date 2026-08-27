# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _material(**overrides):
    fields = {
        "doctype": "Maintenance Material",
        "material_name": "_T-Material " + frappe.generate_hash(length=6),
        "material_category": "Electrical",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestMaterialNameIsTheRecordName(FrappeTestCase):
    def test_the_material_name_becomes_the_record_name(self):
        doc = _material().insert(ignore_permissions=True)
        self.assertEqual(doc.name, doc.material_name)

    def test_framework_refuses_a_second_material_carrying_the_same_name(self):
        first = _material().insert(ignore_permissions=True)
        with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
            _material(material_name=first.material_name).insert(ignore_permissions=True)

    def test_the_naming_field_refuses_to_be_empty(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Material Name is required"):
            _material(material_name=None).insert(ignore_permissions=True)


class TestMaterialCategory(FrappeTestCase):
    def test_an_omitted_category_falls_to_the_first_declared_option_rather_than_being_refused(self):
        doc = _material(material_category=None).insert(ignore_permissions=True)
        self.assertEqual(doc.material_category, "Electrical")

    def test_framework_refuses_a_category_outside_the_select_options(self):
        with self.assertRaisesRegex(frappe.ValidationError, 'cannot be "Landscaping"'):
            _material(material_category="Landscaping").insert(ignore_permissions=True)


class TestMaterialErpnextItemAndDefaults(FrappeTestCase):
    def test_framework_refuses_an_erpnext_item_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _material(erpnext_item="No Such Item " + frappe.generate_hash(length=6)).insert(
                ignore_permissions=True
            )

    def test_a_new_material_is_active_and_measured_in_pieces_by_default(self):
        doc = _material().insert(ignore_permissions=True)
        self.assertEqual(doc.is_active, 1)
        self.assertEqual(doc.default_uom, "Piece")
