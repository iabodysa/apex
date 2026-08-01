# Copyright (c) 2026, AFMCO and contributors
"""A /fleet refusal is resolved in the language the REQUEST declares, not the stored one.

The portal language toggles client-side, so an operator can be reading a fully Arabic
page while their User record still says ``en`` — and ``frappe.throw(_(...))`` resolved
against the stored language, which is how an Arabic page ended up showing an English
refusal.

Frappe already owns the per-request mechanism and it needs no shim: ``get_language``
takes ``frappe.form_dict._lang`` FIRST (``frappe/translate.py:46-49``), ahead of the
logged-in short-circuit that returns the stored language (``:52-53``), and every request
applies it once at ``frappe/auth.py:47``. These tests pin that precedence and pin that
the fleet refusals actually have Arabic to resolve to — the two halves that make a
caller-declared language enough, without ever writing to ``User.language``.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.translate import get_language

from apex.salis.api import fleet_employee

# The refusal an ordinary employee meets on the fuel form: no fleet vehicle is theirs.
REFUSAL = "No fleet vehicle is assigned to you, so you cannot request fuel."
PROBE = "fleet_lang_probe@example.com"


class TestFleetEmployeeRequestLanguage(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        # No role: /fleet is open to any logged-in user and scopes per-user server-side.
        if not frappe.db.exists("User", PROBE):
            frappe.get_doc({"doctype": "User", "email": PROBE, "first_name": "Fleet Lang",
                            "send_welcome_email": 0}).insert(ignore_permissions=True)
        cls.employee_user = PROBE
        frappe.db.set_value("User", PROBE, "language", "en")

    def setUp(self):
        frappe.set_user("Administrator")
        self._lang = frappe.local.lang
        self._form = frappe.local.form_dict

    def tearDown(self):
        frappe.local.lang = self._lang
        frappe.local.form_dict = self._form
        frappe.set_user("Administrator")

    def test_a_declared_language_outranks_the_stored_one(self):
        self.assertTrue(
            frappe.db.exists("Language", "ar"), "Arabic must be an installed Language"
        )
        frappe.set_user(self.employee_user)
        frappe.local.lang = "en"
        frappe.local.form_dict = frappe._dict({"_lang": "ar"})
        # Exactly what auth.py:47 does once per request.
        self.assertEqual(get_language(), "ar")
        # And the operator's own record is untouched by it.
        self.assertEqual(
            frappe.db.get_value("User", self.employee_user, "language"), "en"
        )

    def test_the_fuel_refusal_resolves_in_the_declared_language(self):
        frappe.set_user(self.employee_user)

        frappe.local.lang = "en"
        with self.assertRaises(frappe.PermissionError) as english:
            fleet_employee.submit_fuel_request(litres=10)
        self.assertIn(REFUSAL, frappe.utils.strip_html(str(english.exception)))

        frappe.local.lang = "ar"
        with self.assertRaises(frappe.PermissionError) as arabic:
            fleet_employee.submit_fuel_request(litres=10)
        message = frappe.utils.strip_html(str(arabic.exception))
        self.assertNotIn(REFUSAL, message, "the Arabic page must not be handed English")
        self.assertEqual(message.strip(), frappe._(REFUSAL, lang="ar").strip())
        self.assertEqual(
            frappe.db.get_value("User", self.employee_user, "language"), "en"
        )
