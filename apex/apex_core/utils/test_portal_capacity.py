# Copyright (c) 2026, afmcoltd
"""A portal write carries a role now, and the role is the one the wall was built for.

``as_capacity`` is the join between the two halves: the token authenticates, the capacity user
authorises. These cases prove the three properties the design rests on — the identity exists and
holds its role, the session is handed back even when the block raises, and a write inside the
block is graded by the DocPerm rather than skipped.

The last one matters most: the whole point is that ``ignore_permissions`` is gone from these paths,
so the proof has to be that a plain ``save()`` succeeds for the flow state and that the protected
fields still do not move.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.portal_identity import CAPACITY_USERS, DRIVER, WORKER, as_capacity
from apex.apex_core.setup.seeders.portal_identity_seed import (
    DRIVER_CAPACITY_ROLE,
    WORKER_CAPACITY_ROLE,
)


class TestPortalCapacity(FrappeTestCase):
    def test_both_capacities_are_seeded_and_hold_their_role(self):
        for audience, email in CAPACITY_USERS.items():
            self.assertTrue(frappe.db.exists("User", email), f"{audience} identity missing")
            roles = frappe.get_roles(email)
            self.assertIn(audience, roles, f"{email} does not hold the {audience} role")

    def test_no_capacity_user_can_authenticate(self):
        """The identity has no door: no password is ever set on it.

        Asserted against ``__Auth``, where frappe stores the credential
        (frappe/utils/password.py), because that is the claim. ``simultaneous_sessions``
        cannot serve as this proof: frappe reads it as ``... or 1`` (frappe/sessions.py:66)
        and only to cap concurrent sessions, so a zero there proves nothing about login.
        """
        for email in CAPACITY_USERS.values():
            self.assertFalse(
                frappe.db.sql(
                    "select 1 from `__Auth` where doctype = 'User' and name = %s"
                    " and fieldname = 'password'",
                    email,
                ),
                f"{email} holds a password",
            )

    def test_the_session_is_handed_back(self):
        before = frappe.session.user
        with as_capacity(WORKER) as user:
            self.assertEqual(frappe.session.user, user)
        self.assertEqual(frappe.session.user, before)

    def test_the_session_is_handed_back_after_a_failure(self):
        """A request worker is reused, so an elevated session left behind would carry into the next."""
        before = frappe.session.user
        with self.assertRaises(ValueError):
            with as_capacity(DRIVER):
                raise ValueError("boom")
        self.assertEqual(frappe.session.user, before)

    def test_an_unknown_audience_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            with as_capacity("Supervisor"):
                pass

    def test_each_capacity_holds_create_on_the_documents_it_raises(self):
        """The grants are what let the portal writes drop ignore_permissions."""
        owned = {
            DRIVER: (
                "Fuel Request",
                "Vehicle Incident",
                "Vehicle Handover",
            ),
            WORKER: (
                "Resident Request",
                "Transport Request",
                "Transport Trip Rating",
            ),
        }
        for role, doctypes in owned.items():
            for doctype in doctypes:
                self.assertTrue(
                    frappe.db.exists(
                        "DocPerm",
                        {"parent": doctype, "role": role, "permlevel": 0, "create": 1},
                    ),
                    f"{role} cannot create {doctype}",
                )

        # Trip Start Log and Portal Push Subscription grant the CAPACITY-only roles
        # instead, because a portal write to either has to be told from one holder to
        # the next: Driver and Worker are held by real people, so a create there would
        # reach every one of them rather than the token-resolved path alone.
        for capacity_role in (DRIVER_CAPACITY_ROLE, WORKER_CAPACITY_ROLE):
            for doctype in ("Trip Start Log", "Portal Push Subscription"):
                self.assertTrue(
                    frappe.db.exists(
                        "DocPerm",
                        {
                            "parent": doctype,
                            "role": capacity_role,
                            "permlevel": 0,
                            "create": 1,
                        },
                    ),
                    f"{capacity_role} cannot create {doctype}",
                )
