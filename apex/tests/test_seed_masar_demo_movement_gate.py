# Copyright (c) 2026, AFMCO and contributors
"""Regression guard: the Masar demo-movement seeder runs ONLY on a developer/demo
site, never on a production migrate.

``patches/v1_x/seed_masar_demo_movement.execute`` is registered in patches.txt and
so fires on every ``bench migrate``. Its first act is a ``developer_mode`` gate
(``if not frappe.conf.get("developer_mode"): return``); without that gate a
production migrate would create a demo User, grant it the Driver role, and insert
demo movement records (Dispatch Trip / Route Plan / Transport Request / token).

This proves the gate short-circuits: with ``developer_mode`` off, ``execute()``
creates nothing - it never reaches the DocType-existence check or any seeding
helper, and the demo User stays absent. The dev path (gate on) is asserted to fall
through past the gate to the next guard. Both run with the seeding helpers mocked,
so the test asserts control flow and writes no rows (bench-state independent).
"""

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from apex.patches.v1_x import seed_masar_demo_movement as seed


class TestSeedMasarDemoMovementGate(FrappeTestCase):
    def test_production_migrate_seeds_nothing(self):
        # [#bmjcos]
        with patch.object(seed.frappe, "conf", new={"developer_mode": None}), patch.object(
            seed, "resolve_company_or_any"
        ) as company, patch.object(seed, "_driver_user") as driver_user, patch.object(
            seed, "_driver"
        ) as driver, patch.object(
            seed, "_employee"
        ) as employee, patch.object(
            seed, "_transport_request"
        ) as transport_request, patch.object(
            seed, "_route_plan"
        ) as route_plan, patch.object(
            seed, "_dispatch_trip"
        ) as dispatch_trip, patch.object(
            seed, "_worker_token"
        ) as worker_token:
            seed.execute()

        for helper in (
            company,
            driver_user,
            driver,
            employee,
            transport_request,
            route_plan,
            dispatch_trip,
            worker_token,
        ):
            self.assertFalse(
                helper.called,
                f"production migrate must not seed: {helper} was called",
            )

        # [#h2mm2x]
        self.assertFalse(
            driver_user.called,
            "production migrate must not create the demo driver User",
        )

    def test_dev_site_passes_the_developer_mode_gate(self):
        # [#l13w0j]
        with patch.object(seed.frappe, "conf", new={"developer_mode": 1}), patch.object(
            seed.frappe.db, "exists", return_value=False
        ) as exists:
            seed.execute()

        self.assertTrue(
            exists.called,
            "dev site must pass the developer_mode gate and reach the DocType check",
        )
