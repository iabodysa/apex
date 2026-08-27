# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.desk.form.load import getdoc
from frappe.tests.utils import FrappeTestCase


def _site(**overrides):
    fields = {
        "doctype": "Site",
        "site_name": "_T-Site " + frappe.generate_hash(length=6),
        "status": "Active",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestSiteNameIsTheRecordName(FrappeTestCase):
    def test_the_site_name_becomes_the_record_name(self):
        doc = _site().insert(ignore_permissions=True)
        self.assertEqual(doc.name, doc.site_name)

    def test_framework_refuses_a_second_site_carrying_the_same_name(self):
        first = _site().insert(ignore_permissions=True)
        with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
            _site(site_name=first.site_name).insert(ignore_permissions=True)

    def test_the_naming_field_refuses_to_be_empty(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Site Name is required"):
            _site(site_name=None).insert(ignore_permissions=True)


class TestSiteStatusAndCity(FrappeTestCase):
    def test_framework_refuses_a_status_outside_the_select_options(self):
        with self.assertRaisesRegex(frappe.ValidationError, 'cannot be "Dormant"'):
            _site(status="Dormant").insert(ignore_permissions=True)

    def test_framework_refuses_a_city_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _site(city="Atlantis " + frappe.generate_hash(length=6)).insert(ignore_permissions=True)

    def test_the_declared_status_default_is_applied_server_side(self):
        doc = frappe.get_doc({
            "doctype": "Site",
            "site_name": "_T-Site " + frappe.generate_hash(length=6),
        }).insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Active")


class TestSiteCarriesAddressAndContactOnLoad(FrappeTestCase):
    def test_the_form_load_endpoint_returns_the_address_and_contact_lists(self):
        doc = _site().insert(ignore_permissions=True)
        frappe.response.docs = []
        getdoc("Site", doc.name)
        onload = frappe.response.docs[0].get("__onload") or {}
        self.assertIn("addr_list", onload)
        self.assertIn("contact_list", onload)
