# Copyright (c) 2026, AFMCO and contributors
"""Regression guard: the demo role-login seeder is UN-WIRED from patches.txt
(A-070), so a normal ``bench migrate`` never creates its demo login personas.

``patches/v1_x/seed_demo_role_logins`` used to be registered in patches.txt and
fired on every migrate behind a ``developer_mode`` gate. A-070 removed that
registration entirely: the module stays on disk for a manual, developer-only run
(``bench --site <site> execute apex.patches.v1_x.seed_demo_role_logins.execute``),
but a normal migrate must NOT run it. That module path is the whole recipe — it
ships in the published tree, so the command above resolves in a fresh checkout.

Two guards, either of which fails the build the moment the seeder is re-wired:

  * the module path is absent from patches.txt as an active entry, and
  * on a migrate-only site the two demo login Users (and the demo Employee that
    carries the Masar token) it would create are all absent.

A third guard covers the password. The seeder used to carry the demo login
password as a literal, which made it a working credential in public source,
identical on every checkout. It now reads ``APEX_DEMO_PASSWORD`` from the
operator's environment and refuses to run without it, so two more assertions
hold: an unset variable stops the run with a message naming the variable, and no
password string reaches the User record from inside this module.

The import of the seeder module below is deliberate: it keeps the module
referenced for the dead-code guard (the modules are kept, only un-wired) and lets
the assertions key off the seeder's own demo constants, so they can never drift
from what the seeder would actually create.
"""

import ast
import os
from unittest import mock

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
            f"{_PATCH} must stay UN-WIRED from patches.txt: a normal "
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
                "from patches.txt so a normal migrate never creates it",
            )
        self.assertFalse(
            frappe.db.exists("Employee", {"employee_name": seed._EMP_NAME}),
            f"demo Employee {seed._EMP_NAME!r} (which carries the demo Masar "
            "Worker Token) exists — a normal migrate must not seed it (the "
            "seeder is un-wired)",
        )


class TestSeedDemoRoleLoginsPassword(FrappeTestCase):
    def test_execute_stops_when_the_password_variable_is_unset(self):
        """No variable, no run — and the operator is told which one is missing.

        The check sits ahead of the seeder's own try/except so the failure
        surfaces to the caller instead of being swallowed into the error log,
        and ahead of any database work so this assertion cannot seed anything.
        """
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(seed._PASSWORD_ENV, None)
            with self.assertRaises(RuntimeError) as raised:
                seed.execute()
        self.assertIn(
            seed._PASSWORD_ENV,
            str(raised.exception),
            "the refusal must NAME the variable the operator has to set, "
            "otherwise the message is not actionable",
        )

    def test_password_comes_from_the_environment_unchanged(self):
        """Whatever the operator exports is what the demo logins get — no
        transformation, and no fallback to substitute for a missing value."""
        chosen = frappe.generate_hash(length=20)
        with mock.patch.dict(os.environ, {seed._PASSWORD_ENV: chosen}):
            self.assertEqual(seed._demo_password(), chosen)

    def test_module_ships_no_password_of_its_own(self):
        """The regression this guard exists for: a password written into the
        source is a live credential every checkout shares.

        Structural rather than textual — it fails on ANY literal handed to the
        User record's ``new_password``, not just the one that was removed, and
        it survives renaming or moving the value it does allow.
        """
        with open(seed.__file__, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=seed.__file__)

        literals = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Dict)
            for key, value in zip(node.keys, node.values)
            if isinstance(key, ast.Constant)
            and key.value == "new_password"
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ]
        self.assertEqual(
            literals,
            [],
            f"{seed.__file__} assigns a string literal to `new_password` "
            f"(line(s) {literals}). The demo password must come from "
            f"{seed._PASSWORD_ENV} at runtime — a literal here ships a working "
            "login in public source.",
        )
