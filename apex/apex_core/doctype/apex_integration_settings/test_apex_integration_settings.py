# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Apex Integration Settings controller.

Exercises the frontend base URL validate() gate: an http(s) URL (or a blank
value) saves, anything else is rejected. Requires a live site (Single doc)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.apex_integration_settings.apex_integration_settings import (
    get_integration_settings,
)


class TestApexIntegrationSettings(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.doc = frappe.get_single("Apex Integration Settings")

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
