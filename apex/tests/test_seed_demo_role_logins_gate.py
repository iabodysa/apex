# Copyright (c) 2026, AFMCO and contributors
"""Regression guard: the demo role-login seeder is UN-WIRED from patches.txt
(A-070), so a normal ``bench migrate`` never creates its demo login personas.

``patches/v1_x/seed_demo_role_logins`` used to be registered in patches.txt and
fired on every migrate behind a ``developer_mode`` gate. A-070 removed that
registration entirely: the module stays on disk for a manual, developer-only run
(``bench --site <site> execute apex.patches.v1_x.seed_demo_role_logins.execute``,
mirroring apex/demo/demo_rich.py), but a normal migrate must NOT run it.

Two guards, either of which fails the build the moment the seeder is re-wired:

  * the module path is absent from patches.txt as an active entry, and
  * on a migrate-only site the two demo login Users (and the demo Employee that
    carries the Masar token) it would create are all absent.

The import of the seeder module below is deliberate: it keeps the module
referenced for the dead-code guard (the modules are kept, only un-wired) and lets
the assertions key off the seeder's own demo constants, so they can never drift
from what the seeder would actually create.
"""

import os

import frappe
from frappe.tests.utils import FrappeTestCase

import apex
from apex.patches.v1_x import seed_demo_role_logins as seed

_PATCH = "apex.patches.v1_x.seed_demo_role_logins"


class TestSeedDemoRoleLoginsGate(FrappeTestCase):
    def test_seeder_unwired_from_patches_txt(self):
        """A-070: the demo role-login seeder must NOT be an active patches.txt
        entry, so a normal migrate never runs it. Fails if it is ever re-wired."""
        patches_txt = os.path.join(os.path.dirname(apex.__file__), "patches.txt")
        with open(patches_txt, encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh]

        self.assertNotIn(
            _PATCH,
            lines,
            f"{_PATCH} must stay UN-WIRED from patches.txt (A-070): a normal "
            "migrate must not seed demo logins. Keep the module on disk for a "
            "manual `bench execute` run instead of re-adding it here.",
        )

    def test_migrate_creates_no_demo_login_users(self):
        """On a migrate-only site the seeder never runs, so its demo login Users
        (and the demo Employee that carries the Masar token) are absent. Re-wiring
        it would make the next migrate create them and fail this guard."""
        for email in (seed._SUP_USER, seed._EMP_USER):
            self.assertFalse(
                frappe.db.exists("User", email),
                f"demo login User {email} exists — the seeder must be un-wired "
                "from patches.txt so a normal migrate never creates it (A-070)",
            )
        self.assertFalse(
            frappe.db.exists("Employee", {"employee_name": seed._EMP_NAME}),
            f"demo Employee {seed._EMP_NAME!r} (which carries the demo Masar "
            "Worker Token) exists — a normal migrate must not seed it (seeder "
            "un-wired, A-070)",
        )
