# Copyright (c) 2026, Apex contributors

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.website.path_resolver import resolve_redirect


class TestHousingCountRoute(FrappeTestCase):
    def test_the_route_the_workspaces_link_to_reaches_the_portal_count(self):
        self.addCleanup(setattr, frappe.local.flags, "redirect_location", None)
        frappe.cache.hdel("website_redirects", "housing-count")
        with self.assertRaises(frappe.Redirect):
            resolve_redirect("housing-count")
        self.assertEqual(frappe.local.flags.redirect_location, "/housing#/count")
