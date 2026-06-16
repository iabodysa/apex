# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors
# [#gi2kqa]

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSalisPortalTheme(FrappeTestCase):
    def test_invalid_theme_rejected(self):
        """validate() defends against a direct API write smuggling in an unknown
        theme slug (which would otherwise silently fall back to the default at
        render time). Exercise the controller guard directly so the test targets the
        guard rather than the Select field's own option validation."""
        doc = frappe.get_single("Salis Portal Theme")
        doc.theme = "Not A Real Theme"
        with self.assertRaises(frappe.ValidationError):
            doc.validate()
