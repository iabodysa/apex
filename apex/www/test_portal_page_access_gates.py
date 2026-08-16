# Copyright (c) 2026, afmcoltd
"""Access gates of every www portal door: who is redirected, who is refused, who is let in. consolidated four files that had drifted into copies of one another —
test_housing_count_page_access_gate.py, test_safety_page_access_gate.py,
test_fleet_page_access_gate.py and test_masar_supervisor_page_access_gate.py. Each carried
its own ``capabilities_of`` helper, its own identical ``setUp``, and its own copy of the
same three cases differing only in the module, the route string and the role name. That is
one parameterised case, and it is now ``GATED_SURFACES`` below. Every distinct value the
four files carried is still driven; nothing was dropped to make the table tidy.

THESE ASSERTIONS TARGET WHERE THE GATE LIVES. Every portal door goes through
``publish_portal_context`` (apex_core/utils/portal_bootstrap.py:132), which issues the CSRF
token to every AUTHENTICATED caller as part of the shared shell, and expresses the gate as
``boot["apex_portal"]["capabilities"]`` — an empty list for a user the role check refused.
Asserting against ``ctx.has_portal_role``, ``ctx.can_view``, ``ctx.has_fleet_role``, or a
missing csrf_token instead proves nothing: none of those fields exist on the context this
function publishes, so the assertion would pass on ``None`` without checking anything.

Two doors are NOT in the table because their contract is genuinely different, and each
keeps its own case below:

  /fleet is the EMPLOYEE self-service page (my vehicle / fuel / my trips). ANY logged-in
  user may open it — no fleet role is required — and the shell is handed
  ``fleet.self.read``. Data is scoped PER-USER server-side, so an ordinary employee opening
  it can never reach another user's data. A regression that handed it
  ``fleet.operations.read`` would expose the live supervisor board; a regression that
  withheld ``fleet.self.read`` would break the employee page.

  The controller-filename shape is an app-wide scan, not a per-door check. Frappe resolves
  a www page's controller by replacing hyphens with underscores in the template basename,
  so ``masar-supervisor.html`` looks for ``masar_supervisor.py``. A hyphenated
  ``masar-supervisor.py`` is not a valid Python module name, is never imported, and its
  ``get_context`` never runs — the page then falls through to the no-role branch for EVERY
  user, which is exactly how a genuine Fleet Supervisor once saw the no-access screen.

Identities come from ``apex.tests._helpers._user`` — the shared get-or-create — instead of
a private copy of the same User builder, and ``as_user`` restores the session user rather
than a try/finally in every case.
"""

from __future__ import annotations

from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

import apex.www
from apex.tests._helpers import _user, as_user
from apex.www import fleet, fleet_os, housing, masar_supervisor, safety


def capabilities_of(context):
    return context.boot["apex_portal"]["capabilities"]


# (label, controller module, route, refused role, admitted roles, capability that must be
# granted or None for "any capability at all"). "Internal Auditor" is the refused role
# throughout: a real shipped role that holds none of the portal role sets, so a gate that
# admitted it would be admitting everyone. Safety Officer is ADMITTED on /safety on purpose
# — a maker who cannot submit still records a round for a supervisor to close, so refusing
# it would turn a role away from a portal it can use.
GATED_SURFACES = (
    ("housing", housing, "/housing", "Internal Auditor", ("Accommodation Manager",), None),
    (
        "safety",
        safety,
        "/safety",
        "Internal Auditor",
        ("Accommodation Manager", "Safety Officer"),
        None,
    ),
    (
        "fleet-os board",
        fleet_os,
        "/fleet-os",
        "Internal Auditor",
        ("Fleet Manager",),
        "fleet.operations.read",
    ),
    (
        "masar-supervisor",
        masar_supervisor,
        "/masar-supervisor",
        "Internal Auditor",
        ("Fleet Supervisor",),
        None,
    ),
)


def _identity(label, suffix, role):
    """A stable per-surface probe user, so the get-or-create hits the same row each run."""
    return _user(f"gate-{label.split()[0]}-{suffix}@test.local", role)


class TestPortalPageAccessGates(FrappeTestCase):
    def setUp(self):
        # render_in_arabic() writes frappe.local.lang for the rest of the render. In a
        # request that local dies with the request; in a test run it does not, so it is
        # handed back rather than left for whatever runs next.
        self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)

    def test_a_guest_is_redirected_to_login_and_back(self):
        for label, module, route, _refused, _admitted, _capability in GATED_SURFACES:
            with self.subTest(surface=label):
                with as_user("Guest"):
                    with self.assertRaises(frappe.Redirect):
                        module.get_context(frappe._dict())
                    self.assertEqual(
                        frappe.local.flags.redirect_location,
                        f"/login?redirect-to={route}",
                        f"a Guest must be sent to login and back to {route}",
                    )

    def test_a_user_without_the_portal_role_gets_no_capabilities(self):
        for label, module, _route, refused, _admitted, _capability in GATED_SURFACES:
            with self.subTest(surface=label, role=refused):
                with as_user(_identity(label, "norole", refused)):
                    ctx = module.get_context(frappe._dict())
                    self.assertEqual(
                        capabilities_of(ctx),
                        [],
                        f"a {refused} must not pass the {label} gate",
                    )

    def test_a_user_holding_the_portal_role_gets_capabilities_and_a_csrf_token(self):
        for label, module, _route, _refused, admitted, capability in GATED_SURFACES:
            for role in admitted:
                with self.subTest(surface=label, role=role):
                    with as_user(_identity(label, role.split()[0].lower(), role)):
                        ctx = module.get_context(frappe._dict())
                        granted = capabilities_of(ctx)
                        if capability:
                            self.assertIn(
                                capability,
                                granted,
                                f"a {role} must be handed {capability} on {label}",
                            )
                        else:
                            self.assertTrue(
                                granted, f"a {role} must pass the {label} gate"
                            )
                        self.assertTrue(
                            ctx.csrf_token,
                            f"the {label} portal's POSTs need a CSRF token",
                        )

    def test_a_system_manager_passes_every_gate(self):
        """The role that holds no portal role set but must never be locked out. Run as
        the session's own Administrator, which is how a desk operator arrives."""
        for label, module, _route, _refused, _admitted, _capability in GATED_SURFACES:
            with self.subTest(surface=label):
                self.assertTrue(
                    capabilities_of(module.get_context(frappe._dict())),
                    f"a System Manager must pass the {label} gate",
                )

    def test_the_employee_fleet_page_admits_any_logged_in_user_without_the_board(self):
        """/fleet is not gated on a fleet role; per-user scoping is what protects it."""
        with as_user(_user("gate-fleet-norole@test.local", "Internal Auditor")):
            ctx = fleet.get_context(frappe._dict())
            granted = capabilities_of(ctx)
            self.assertIn(
                "fleet.self.read", granted, "any logged-in user may open the employee page"
            )
            self.assertNotIn(
                "fleet.operations.read",
                granted,
                "the employee page never grants the supervisor board's capability",
            )
            self.assertTrue(ctx.csrf_token, "the employee page's POSTs need a CSRF token")

    def test_the_employee_fleet_page_still_redirects_a_guest(self):
        with as_user("Guest"):
            with self.assertRaises(frappe.Redirect):
                fleet.get_context(frappe._dict())
            self.assertEqual(
                frappe.local.flags.redirect_location,
                "/login?redirect-to=/fleet",
                "a Guest must be sent to login and back to /fleet",
            )

    def test_each_door_lands_on_its_own_screen(self):
        """/safety and /housing are one app; the door decides where it lands."""
        with as_user(_user("gate-safety-accommodation@test.local", "Accommodation Manager")):
            self.assertEqual(
                safety.get_context(frappe._dict())["boot"]["apex_portal"]["initial_route"],
                "/rounds",
            )
            self.assertNotEqual(
                housing.get_context(frappe._dict())["boot"]["apex_portal"]["initial_route"],
                "/rounds",
            )

    def test_no_www_controller_filename_has_a_hyphen(self):
        # A hyphenated *.py controller is never importable, so its get_context never runs.
        www_dir = Path(apex.www.__file__).parent
        controllers = sorted(p.name for p in www_dir.glob("*.py"))
        self.assertTrue(controllers, "the www controller scan read an empty directory")
        offenders = [name for name in controllers if "-" in name]
        self.assertEqual(
            offenders,
            [],
            f"www controller filenames must use underscores, not hyphens: {offenders}",
        )
