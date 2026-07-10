# Copyright (c) 2026, AFMCO and contributors
"""Regression guard: the demo role-login seeder runs ONLY on a developer/demo
site, never on a production migrate.

``patches/v1_x/seed_demo_role_logins.execute`` is registered in patches.txt and
so fires on every ``bench migrate``. Its first act is a ``developer_mode`` gate
(``if not frappe.conf.get("developer_mode"): return``); without that gate a
production migrate would create demo Users, grant them roles, and seed demo
rooms / snapshots / a safety round.

This proves the gate short-circuits: with ``developer_mode`` off, ``execute()``
creates nothing — it never reaches the DocType-existence check or any seeding
helper, and the demo Users stay absent. The dev path (gate on) is asserted to
fall through past the gate to the next guard. Both run with the seeding helpers
mocked, so the test asserts control flow and writes no rows (bench-state
independent).
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v1_x import seed_demo_role_logins as seed


class TestSeedDemoRoleLoginsGate(FrappeTestCase):
    def test_production_migrate_seeds_nothing(self):
        # [#9xrhnc]
        with patch.object(
            seed.frappe, "conf", new=frappe._dict(developer_mode=None)
        ), patch.object(seed, "resolve_company_or_any") as company, patch.object(
            seed, "_seed_supervisor"
        ) as seed_supervisor, patch.object(seed, "_seed_employee") as seed_employee:
            result = seed.execute()

        self.assertIsNone(result, "production migrate must return no recipe")
        for helper in (company, seed_supervisor, seed_employee):
            self.assertFalse(
                helper.called,
                f"production migrate must not seed: {helper} was called",
            )

    def test_dev_site_passes_the_developer_mode_gate(self):
        # [#l13w0j]
        with patch.object(
            seed.frappe, "conf", new=frappe._dict(developer_mode=1)
        ), patch.object(
            seed.frappe.db, "exists", return_value=False
        ) as exists, patch.object(seed, "_seed_supervisor") as seed_supervisor:
            seed.execute()

        self.assertTrue(
            exists.called,
            "dev site must pass the developer_mode gate and reach the DocType check",
        )
        self.assertFalse(
            seed_supervisor.called,
            "a missing DocType must stop the seeder before any persona is built",
        )

    def test_dev_site_returns_both_login_recipes(self):
        # [#jc2zqp]
        with patch.object(
            seed.frappe, "conf", new=frappe._dict(developer_mode=1)
        ), patch.object(seed.frappe.db, "exists", return_value=True), patch.object(
            seed.frappe.db, "commit"
        ), patch.object(seed, "resolve_company_or_any", return_value="Demo Co"), patch.object(
            seed, "_seed_supervisor"
        ) as seed_supervisor, patch.object(
            seed, "_seed_employee", return_value="tok_demo_123"
        ) as seed_employee, patch.object(
            seed.frappe.utils, "get_url", return_value="http://demo.localhost"
        ):
            result = seed.execute()

        self.assertTrue(seed_supervisor.called, "dev site must seed the supervisor")
        self.assertTrue(seed_employee.called, "dev site must seed the employee")
        self.assertIsInstance(result, dict)

        sup = result["supervisor"]
        self.assertEqual(sup["email"], seed._SUP_USER)
        self.assertEqual(sup["password"], seed._DEMO_PASSWORD)
        self.assertEqual(sup["scoped_building"], seed._BUILDING)
        self.assertIn("Resident Supervisor", sup["roles"])
        self.assertIn("Fleet Supervisor", sup["roles"])

        emp = result["employee"]
        self.assertEqual(emp["email"], seed._EMP_USER)
        self.assertEqual(emp["password"], seed._DEMO_PASSWORD)
        # [#mras1v]
        self.assertEqual(emp["masar_link"], "http://demo.localhost/masar?w=tok_demo_123")
