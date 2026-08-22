# Copyright (c) 2026, afmcoltd
"""Site's own contract: it is named by its site_name, and that name is unique.

The uniqueness case borrows the record from ``test_records.json`` rather than inserting one to
collide with — the fixture already stands, so the test asserts the rule instead of arranging it.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Site"]

class TestSite(FrappeTestCase):
    def test_a_site_is_named_by_its_site_name(self):
        site = frappe.get_doc({
            "doctype": "Site",
            "site_name": "_T Site Riyadh",
            "city": "Riyadh",
            "status": "Active",
        })
        site.insert(ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Site", site.name, force=True, ignore_permissions=True)

        self.assertEqual(site.name, "_T Site Riyadh")

    def test_a_site_without_a_name_is_refused(self):
        site = frappe.get_doc({"doctype": "Site", "city": "Jeddah"})

        with self.assertRaises(frappe.exceptions.ValidationError):
            site.insert(ignore_permissions=True)

    def test_a_second_site_cannot_take_a_name_already_in_use(self):
        duplicate = frappe.get_doc({"doctype": "Site", "site_name": "_Test Site"})

        with self.assertRaises(frappe.DuplicateEntryError):
            duplicate.insert(ignore_permissions=True)
