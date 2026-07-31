# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Apex Integration Settings controller and its shipped help panel.

Exercises the frontend base URL validate() gate: an http(s) URL (or a blank
value) saves, anything else is rejected. Also holds the help panel to the
authentication rule the integration guide states: the API key and secret recipe
belongs to a client that can keep a secret, and a browser or store-installed
client is sent to native OAuth or a backend-for-frontend instead. The panel is
read from the imported DocType default, which is what a site renders after
migrate; the copy stored in tabSingles is re-seeded by
apex.patches.v2_1.refresh_integration_settings_help.

Requires a live site (Single doc)."""

from __future__ import annotations

import re

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.apex_integration_settings.apex_integration_settings import (
    get_integration_settings,
)

LIST_ITEM = re.compile(r"<li>(.*?)</li>", re.S)


class TestApexIntegrationSettings(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.doc = frappe.get_single("Apex Integration Settings")
        # A Single lives in tabSingles, outside any row this test created, and
        # FrappeTestCase only rolls back once per CLASS — so snapshot the deployment
        # value and register the restore BEFORE the first mutating save below.
        self._frontend_base_url = self.doc.frontend_base_url
        self.addCleanup(self._restore_settings)

    def _restore_settings(self):
        doc = frappe.get_single("Apex Integration Settings")
        doc.frontend_base_url = self._frontend_base_url
        doc.save(ignore_permissions=True)

    def test_https_url_is_accepted(self):
        self.doc.frontend_base_url = "https://salis-fleet.com"
        self.doc.save(ignore_permissions=True)
        self.assertEqual(self.doc.frontend_base_url, "https://salis-fleet.com")

    def test_http_url_is_accepted(self):
        self.doc.frontend_base_url = "http://localhost:8080"
        self.doc.save(ignore_permissions=True)
        self.assertEqual(self.doc.frontend_base_url, "http://localhost:8080")

    def test_blank_url_is_allowed(self):
        self.doc.frontend_base_url = ""
        self.doc.save(ignore_permissions=True)  # must not raise

    def test_scheme_less_url_is_rejected(self):
        self.doc.frontend_base_url = "salis-fleet.com"
        with self.assertRaises(frappe.exceptions.ValidationError):
            self.doc.save(ignore_permissions=True)

    def test_non_http_scheme_is_rejected(self):
        self.doc.frontend_base_url = "ftp://salis-fleet.com"
        with self.assertRaises(frappe.exceptions.ValidationError):
            self.doc.save(ignore_permissions=True)

    def test_get_integration_settings_returns_the_single(self):
        settings = get_integration_settings()
        self.assertEqual(settings.doctype, "Apex Integration Settings")

    def _help_items(self):
        panel = frappe.get_meta("Apex Integration Settings").get_field("integration_help").default
        items = LIST_ITEM.findall(panel or "")
        self.assertTrue(items, "the integration help panel must list the linking options")
        return items

    def _browser_item(self):
        items = [item for item in self._help_items() if "browser" in item.lower()]
        self.assertEqual(len(items), 1, "the panel must address a browser client exactly once")
        return items[0].lower()

    def test_the_token_recipe_is_scoped_to_a_client_that_can_keep_a_secret(self):
        carriers = [item for item in self._help_items() if "Authorization: token" in item]
        self.assertEqual(len(carriers), 1, "one panel item may carry the key and secret recipe")
        item = carriers[0].lower()
        self.assertIn("confidential client", item)
        self.assertNotIn("browser", item)

    def test_a_public_client_is_told_to_hold_no_secret(self):
        item = self._browser_item()
        self.assertIn("never", item)
        self.assertIn("secret", item)
        self.assertNotIn("authorization: token", item)

    def test_a_public_client_is_offered_oauth_or_a_backend_for_frontend(self):
        item = self._browser_item()
        self.assertIn("oauth client", item)
        self.assertIn("pkce", item)
        self.assertIn("backend-for-frontend", item)
