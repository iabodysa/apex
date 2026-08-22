# Copyright (c) 2026, afmcoltd
"""What Apex Integration Settings guarantees, asserted against the DocType itself.

Patterned on frappe's own document-validation tests (``frappe/tests/test_document.py``,
``test_validate``). This is a Single — one standing row, never inserted fresh — so every
case reads it with ``frappe.get_single`` and restores whatever it changes.

The one guarantee: a non-blank Frontend Base URL must look like an http(s) URL, so a
pasted value with no scheme never reaches the "add this origin to allow_cors" guidance
silently wrong.
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestApexIntegrationSettings(FrappeTestCase):
    def test_a_frontend_base_url_without_a_scheme_is_refused(self):
        """A URL with no scheme is not something a browser or a CORS origin list can use;
        refusing it here is cheaper than a support ticket about a silently broken
        integration."""
        settings = frappe.get_single("Apex Integration Settings")
        settings.frontend_base_url = "salis-fleet.com"

        with self.assertRaisesRegex(
            frappe.ValidationError, "must start with http"
        ):
            settings.save()

    def test_a_frontend_base_url_with_a_scheme_is_accepted(self):
        """The acceptance counterpart — a well-formed https URL must still save, or the
        refusal above is blocking every value, not just malformed ones."""
        settings = frappe.get_single("Apex Integration Settings")
        original = settings.frontend_base_url
        self.addCleanup(
            frappe.db.set_single_value,
            "Apex Integration Settings",
            "frontend_base_url",
            original,
        )

        settings.frontend_base_url = "https://salis-fleet.example"
        settings.save()

        self.assertEqual(
            frappe.db.get_single_value(
                "Apex Integration Settings", "frontend_base_url"
            ),
            "https://salis-fleet.example",
        )
