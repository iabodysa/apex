# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Salis Settings zero-trap read helpers.

A new Int/Float on an existing Single stores 0 (not its JSON default), so every
numeric read must coalesce a blank/0 value to the caller's default. These tests
pin that behaviour for the canonical get_salis_int / get_salis_float helpers and
for the extracted thresholds that now route through them — proving no caller
trusts a raw 0.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.salis_settings.salis_settings import (
    get_salis_float,
    get_salis_int,
)


class TestSalisSettingsHelpers(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_int_returns_default_when_unset_not_zero(self):
        frappe.db.set_single_value("Salis Settings", "admin_trip_ops_threshold", 0)
        self.assertEqual(get_salis_int("admin_trip_ops_threshold", 5), 5)

    def test_int_returns_stored_nonzero_value(self):
        frappe.db.set_single_value("Salis Settings", "admin_trip_ops_threshold", 9)
        self.assertEqual(get_salis_int("admin_trip_ops_threshold", 5), 9)

    def test_float_returns_default_when_unset_not_zero(self):
        frappe.db.set_single_value("Salis Settings", "writeoff_ops_threshold", 0)
        self.assertEqual(get_salis_float("writeoff_ops_threshold", 2000.0), 2000.0)

    def test_float_returns_stored_nonzero_value(self):
        frappe.db.set_single_value("Salis Settings", "writeoff_ops_threshold", 3500)
        self.assertEqual(get_salis_float("writeoff_ops_threshold", 2000.0), 3500.0)

    def test_license_expiring_warn_days_default(self):
        frappe.db.set_single_value("Salis Settings", "license_expiring_warn_days", 0)
        self.assertEqual(get_salis_int("license_expiring_warn_days", 30), 30)

    def test_fuel_overage_margin_reads_via_helper(self):
        from apex.salis.fuel_engine import get_overage_margin

        frappe.db.set_single_value("Salis Settings", "fuel_overage_margin_percent", 0)
        self.assertAlmostEqual(get_overage_margin(), 0.05)
        frappe.db.set_single_value("Salis Settings", "fuel_overage_margin_percent", 10)
        self.assertAlmostEqual(get_overage_margin(), 0.10)


class TestSalisSettingsPortalAppearance(FrappeTestCase):
    """The two appearance values an operator can type, and what the guard refuses.

    ``accent_color`` and ``brand_logo`` are rendered straight into the portal shell, so a
    value that is not a CSS colour or not an uploaded ``/files/`` path is refused at save
    rather than at render. The guard is exercised directly: the Color and Attach Image
    fieldtypes do not validate their own content, so it is the only thing standing between
    a typed value and the page, and calling it alone keeps this test independent of the
    payroll and web-push checks that share ``validate``.
    """

    def setUp(self):
        frappe.set_user("Administrator")
        self.doc = frappe.get_single("Salis Settings")
        self.doc.accent_color = ""
        self.doc.brand_logo = ""

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_a_valid_accent_and_uploaded_logo_pass(self):
        """Non-vacuity control for the refusals below."""
        self.doc.accent_color = "#1B4D3E"
        self.doc.brand_logo = "/files/apex-brand.png"
        self.doc._validate_portal_appearance()

    def test_blank_values_are_allowed_because_both_fields_are_optional(self):
        self.doc._validate_portal_appearance()

    def test_an_accent_that_is_not_a_css_colour_is_refused(self):
        for accent in ("not a colour", "#12g4h5", "javascript:alert(1)", "url(evil)"):
            with self.subTest(accent=accent):
                self.doc.accent_color = accent
                with self.assertRaises(frappe.ValidationError):
                    self.doc._validate_portal_appearance()

    def test_a_logo_that_is_not_an_uploaded_file_is_refused(self):
        """The path is written into an ``img`` src, so an off-site or markup-bearing
        value must not reach the shell."""
        for logo in (
            "https://evil.example/logo.png",
            "/private/files/secret.png",
            '/files/x"><script>',
        ):
            with self.subTest(logo=logo):
                self.doc.brand_logo = logo
                with self.assertRaises(frappe.ValidationError):
                    self.doc._validate_portal_appearance()
