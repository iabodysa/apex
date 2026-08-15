# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors
"""The two values this Single lets an operator type, and what ``validate`` refuses.

``accent_color`` and ``brand_logo`` are rendered straight into the portal shell, so a
value that is not a CSS colour or not an uploaded ``/files/`` path is refused at save
rather than at render. The controller is exercised directly: the Color and Attach Image
fieldtypes do not validate their own content, so the guard is the only thing standing
between a typed value and the page.

There is no theme slug — Apex ships one light colour system and this record does not
select a theme, which is why nothing here names one.
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestDriverPortalTheme(FrappeTestCase):
    def setUp(self):
        self.doc = frappe.get_single("Driver Portal Theme")
        self.doc.accent_color = ""
        self.doc.brand_logo = ""

    def test_a_valid_accent_and_uploaded_logo_pass(self):
        """Non-vacuity control for the refusals below."""
        self.doc.accent_color = "#1B4D3E"
        self.doc.brand_logo = "/files/apex-brand.png"
        self.doc.validate()

    def test_blank_values_are_allowed_because_both_fields_are_optional(self):
        self.doc.validate()

    def test_an_accent_that_is_not_a_css_colour_is_refused(self):
        for accent in ("not a colour", "#12g4h5", "javascript:alert(1)", "url(evil)"):
            with self.subTest(accent=accent):
                self.doc.accent_color = accent
                with self.assertRaises(frappe.ValidationError):
                    self.doc.validate()

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
                    self.doc.validate()
