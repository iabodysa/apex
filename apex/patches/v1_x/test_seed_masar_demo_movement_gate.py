# Copyright (c) 2026, AFMCO and contributors
"""Regression guard: the Masar demo-movement seeder is UN-WIRED from patches.txt
(A-070), so a normal ``bench migrate`` never creates its demo movement scenario.

``patches/v1_x/seed_masar_demo_movement`` used to be registered in patches.txt and
fired on every migrate behind a ``developer_mode`` gate. A-070 removed that
registration entirely: the module stays on disk for a manual, developer-only run
(``bench --site <site> execute apex.patches.v1_x.seed_masar_demo_movement.execute``),
but a normal migrate must NOT run it. That module path is the whole recipe — it
ships in the published tree, so the command above resolves in a fresh checkout.

Two guards, either of which fails the build the moment the seeder is re-wired:

  * the module path is absent from patches.txt as an active entry, and
  * on a migrate-only site the demo User / Building / Trip (via its Route Plan) /
    worker Employee (which carries the Masar token) it would create are all absent.

The import of the seeder module below is deliberate: it keeps the module
referenced for the dead-code guard (the modules are kept, only un-wired) and lets
the assertions key off the seeder's own demo constants, so they can never drift
from what the seeder would actually create.
"""

import os

import frappe
from frappe.tests.utils import FrappeTestCase

import apex
from apex.patches.v1_x import seed_masar_demo_movement as seed

_PATCH = "apex.patches.v1_x.seed_masar_demo_movement"


class TestSeedMasarDemoMovementGate(FrappeTestCase):
    def test_seeder_unwired_from_patches_txt(self):
        """A-070: the Masar demo-movement seeder must NOT be an active patches.txt
        entry, so a normal migrate never runs it. Fails if it is ever re-wired."""
        patches_txt = os.path.join(os.path.dirname(apex.__file__), "patches.txt")
        with open(patches_txt, encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh]

        self.assertNotIn(
            _PATCH,
            lines,
            f"{_PATCH} must stay UN-WIRED from patches.txt (A-070): a normal "
            "migrate must not seed the demo movement scenario. Keep the module on "
            "disk for a manual `bench execute` run instead of re-adding it here.",
        )

    def test_migrate_creates_no_demo_movement_records(self):
        """On a migrate-only site the seeder never runs, so its signature records
        are absent. Re-wiring it would make the next migrate create them (the demo
        driver User, the demo Building, the demo Trip via its Route Plan, and the
        demo worker Employee that carries the Masar token) and fail this guard."""
        self.assertFalse(
            frappe.db.exists("User", seed._DEMO_USER),
            f"demo driver User {seed._DEMO_USER} exists — the seeder must be "
            "un-wired from patches.txt so a normal migrate never creates it (A-070)",
        )
        self.assertFalse(
            frappe.db.exists("Building", {"building_name": seed._BUILDING}),
            f"demo Building {seed._BUILDING!r} exists — a normal migrate must not "
            "seed it (seeder un-wired, A-070)",
        )
        self.assertFalse(
            frappe.db.exists("Route Plan", {"route_name": seed._ROUTE}),
            f"demo Route Plan {seed._ROUTE!r} (and its Dispatch Trip) exists — a "
            "normal migrate must not seed it (seeder un-wired, A-070)",
        )
        self.assertFalse(
            frappe.db.exists("Employee", {"employee_name": seed._WORKER_ONE}),
            f"demo worker Employee {seed._WORKER_ONE!r} (which carries the demo "
            "Masar Worker Token) exists — a normal migrate must not seed it "
            "(seeder un-wired, A-070)",
        )
