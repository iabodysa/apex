# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _city(**overrides):
    fields = {
        "doctype": "City",
        "city_name": "_T-City " + frappe.generate_hash(length=6),
        "country": "Saudi Arabia",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestCityNameIsTheRecordName(FrappeTestCase):
    def test_the_city_name_becomes_the_record_name(self):
        doc = _city().insert(ignore_permissions=True)
        self.assertEqual(doc.name, doc.city_name)

    def test_framework_refuses_a_second_city_carrying_the_same_name(self):
        first = _city().insert(ignore_permissions=True)
        with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
            _city(city_name=first.city_name).insert(ignore_permissions=True)

    def test_the_naming_field_refuses_to_be_empty(self):
        with self.assertRaisesRegex(frappe.ValidationError, "City Name is required"):
            _city(city_name=None).insert(ignore_permissions=True)


class TestCityCountry(FrappeTestCase):
    def test_framework_refuses_a_country_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _city(country="Nowhereland " + frappe.generate_hash(length=6)).insert(ignore_permissions=True)

    def test_the_declared_country_default_is_applied_server_side(self):
        doc = frappe.get_doc({
            "doctype": "City",
            "city_name": "_T-City " + frappe.generate_hash(length=6),
        }).insert(ignore_permissions=True)
        self.assertEqual(doc.country, "Saudi Arabia")
