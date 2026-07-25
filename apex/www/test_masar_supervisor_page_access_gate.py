# Copyright (c) 2026, AFMCO and contributors
"""Access gate of the /masar-supervisor Route Supervisor portal (www/masar_supervisor.py).

Two regressions are pinned here:

1. Controller filename shape. Frappe resolves a www page's controller by replacing
   hyphens with underscores in the template basename, so ``masar-supervisor.html`` looks
   for ``masar_supervisor.py`` (underscore). A hyphenated ``masar-supervisor.py`` is not a
   valid Python module name, is never imported, and its ``get_context`` never runs — the
   page then falls through to the no-role branch for EVERY user. This test asserts NO
   controller under apex/www/ carries a hyphen in its .py filename, so the bug cannot
   silently return for this or any other portal.

2. Role gate. Mirrors test_fleet_page_access_gate / test_safety_page_access_gate:
   * a Guest is redirected to /login (then back to /masar-supervisor);
   * a logged-in user WITHOUT a supervisor role gets the friendly no-role page —
     has_supervisor_role is False and NO CSRF token is issued;
   * a Fleet Supervisor gets has_supervisor_role True + a CSRF token for the SPA's
     approve/reject POSTs. This is exactly the case the hyphen bug broke: the controller
     never loaded, so even a genuine Fleet Supervisor saw the no-access screen.
"""

from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.www import masar_supervisor


class TestMasarSupervisorPageAccessGate(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _user_with_roles(self, email, roles):
        if not frappe.db.exists("User", email):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": email.split("@")[0],
                    "roles": [{"role": r} for r in roles],
                }
            ).insert(ignore_permissions=True)
        return email

    def test_no_www_controller_filename_has_a_hyphen(self):
        # A hyphenated *.py controller is never importable, so its get_context never runs.
        www_dir = Path(masar_supervisor.__file__).parent
        offenders = sorted(p.name for p in www_dir.glob("*.py") if "-" in p.name)
        self.assertEqual(
            offenders,
            [],
            f"www controller filenames must use underscores, not hyphens: {offenders}",
        )

    def test_guest_is_redirected_to_login(self):
        frappe.set_user("Guest")
        try:
            with self.assertRaises(frappe.Redirect):
                masar_supervisor.get_context(frappe._dict())
            self.assertEqual(
                frappe.local.flags.redirect_location,
                "/login?redirect-to=/masar-supervisor",
                "a Guest must be sent to login and back to /masar-supervisor",
            )
        finally:
            frappe.set_user("Administrator")

    def test_non_supervisor_role_gets_friendly_no_role_page(self):
        frappe.set_user(self._user_with_roles("masar-sup-gate-norole@test.local", ["Internal Auditor"]))
        try:
            ctx = masar_supervisor.get_context(frappe._dict())
            self.assertFalse(ctx.has_supervisor_role, "a non-supervisor user must not pass the gate")
            self.assertIsNone(ctx.get("csrf_token"), "no CSRF token may be issued to a non-supervisor user")
        finally:
            frappe.set_user("Administrator")

    def test_fleet_supervisor_gets_access_and_csrf(self):
        # The exact case the hyphen bug broke: a real supervisor was shown the no-access screen.
        frappe.set_user(self._user_with_roles("masar-sup-gate-fs@test.local", ["Fleet Supervisor"]))
        try:
            ctx = masar_supervisor.get_context(frappe._dict())
            self.assertTrue(ctx.has_supervisor_role, "a Fleet Supervisor must pass the gate and see the SPA")
            self.assertTrue(ctx.get("csrf_token"), "a supervisor must receive a CSRF token for approve/reject POSTs")
        finally:
            frappe.set_user("Administrator")
