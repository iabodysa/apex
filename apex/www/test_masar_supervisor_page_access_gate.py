# Copyright (c) 2026, afmcoltd
"""Access gate of the /masar-supervisor Route Supervisor portal (www/masar_supervisor.py).

Two regressions are pinned here:

1. Controller filename shape. Frappe resolves a www page's controller by replacing hyphens
   with underscores in the template basename, so ``masar-supervisor.html`` looks for
   ``masar_supervisor.py`` (underscore). A hyphenated ``masar-supervisor.py`` is not a valid
   Python module name, is never imported, and its ``get_context`` never runs — the page then
   falls through to the no-role branch for EVERY user. This test asserts NO controller under
   apex/www/ carries a hyphen in its .py filename, so the bug cannot silently return for
   this or any other portal.

2. Role gate. Mirrors test_fleet_page_access_gate / test_safety_page_access_gate:
   * a Guest is redirected to /login (then back to /masar-supervisor);
   * a logged-in user WITHOUT a supervisor role is bootstrapped with NO capabilities;
   * a Fleet Supervisor is bootstrapped WITH them, plus a CSRF token for the SPA's
     approve/reject POSTs. This is exactly the case the hyphen bug broke: the controller
     never loaded, so even a genuine Fleet Supervisor saw the no-access screen.

THE GATE MOVED, AND THIS FILE FOLLOWED IT — see test_safety_page_access_gate for why
``has_supervisor_role`` and the conditional CSRF token are gone and
``boot["apex_portal"]["capabilities"]`` is what now carries the verdict.

The identities come from ``apex.tests._helpers._user`` — the shared get-or-create — instead
of a private copy of the same User builder.
"""

from __future__ import annotations

from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests._helpers import _user, as_user
from apex.www import masar_supervisor


def capabilities_of(context):
    return context.boot["apex_portal"]["capabilities"]


class TestMasarSupervisorPageAccessGate(FrappeTestCase):
    def setUp(self):
        # render_in_arabic() writes frappe.local.lang for the rest of the render; handed
        # back here because in a test run that local outlives the case.
        self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)

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
        with as_user("Guest"):
            with self.assertRaises(frappe.Redirect):
                masar_supervisor.get_context(frappe._dict())
            self.assertEqual(
                frappe.local.flags.redirect_location,
                "/login?redirect-to=/masar-supervisor",
                "a Guest must be sent to login and back to /masar-supervisor",
            )

    def test_non_supervisor_role_gets_no_capabilities(self):
        with as_user(_user("masar-sup-gate-norole@test.local", "Internal Auditor")):
            ctx = masar_supervisor.get_context(frappe._dict())
            self.assertEqual(
                capabilities_of(ctx), [], "a non-supervisor user must not pass the gate"
            )

    def test_fleet_supervisor_gets_access_and_csrf(self):
        # The exact case the hyphen bug broke: a real supervisor was shown the no-access
        # screen.
        with as_user(_user("masar-sup-gate-fs@test.local", "Fleet Supervisor")):
            ctx = masar_supervisor.get_context(frappe._dict())
            self.assertTrue(
                capabilities_of(ctx),
                "a Fleet Supervisor must pass the gate and see the SPA",
            )
            self.assertTrue(
                ctx.csrf_token,
                "a supervisor must receive a CSRF token for approve/reject POSTs",
            )
