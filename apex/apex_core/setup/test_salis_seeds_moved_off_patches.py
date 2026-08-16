# Copyright (c) 2026, AFMCO and contributors
"""The Salis install seeds no longer live in patches, and nothing imports one.

`salis/setup.py` imported three modules out of `apex/patches/v1_0/` and called their
`execute()` from `after_install`. It was the only import of `apex.patches` anywhere in
the app, and it made retiring those patches — a planned cleanup — an ImportError on every
fresh install rather than the cleanup it looks like. Worse, three of the roles they seed
are provided by nothing else, so the failure would have been a site with no fleet
supervision roles at all.

The seeds now live beside the others in `apex_core/setup/seeders/` and hooks.py runs each
on BOTH `after_install` and `after_migrate`, so a new site and an existing one reach the
same state by the same code.

The role half of the first attempt was WRONG and is corrected here. Frappe already
creates a Role for every role named in a shipped DocType's permissions block —
`make_module_and_roles`, `frappe/core/doctype/doctype/doctype.py:1852` — so a seeder that
created them was dead code. Proved on a clean site built with `bench new-site
--install-app apex`: all five exist. What the framework gets wrong is desk access, which
it sets to 1 for every role it makes, so the seeder now only clears it for the
portal-only Driver — the same narrow correction ERPNext applies to its website roles.
"""

import ast
import json
import pathlib

import frappe
from frappe.tests.utils import FrappeTestCase

from apex import hooks
from apex.apex_core.setup.seeders import salis_portal_theme_seed
from apex.apex_core.setup.seeders.salis_portal_theme_seed import seed_salis_portal_theme
from apex.apex_core.setup.seeders.salis_settings_seed import (
    DEFAULTS as SETTINGS_DEFAULTS,
    seed_salis_settings,
)
from apex.tests.source_tree import is_test_file, rel

APP_ROOT = pathlib.Path(frappe.get_app_path("apex"))

MOVED_SEEDS = (
    "apex.apex_core.setup.seeders.salis_settings_seed.seed_salis_settings",
    "apex.apex_core.setup.seeders.salis_portal_theme_seed.seed_salis_portal_theme",
)


class TestTheSalisSeedsLeftThePatchesDirectory(FrappeTestCase):
    def test_no_module_in_the_app_imports_a_patch(self):
        """The break this card is about. A patch is a one-time migration for sites that
        already exist; importing one into the INSTALL PATH couples every fresh install
        to a file the cleanup is meant to delete. A test file that imports a patch to
        exercise it directly (apex_core/setup/test_backend_board_contract.py,
        patches/v2_6/test_converge_native_support_and_recovery.py) never runs at install
        time, so it carries none of that risk; excluded the same way
        test_db_exists_short_circuit_guard.py excludes the test lane from its own
        production-path scan."""
        importers = []
        for path in APP_ROOT.rglob("*.py"):
            if "__pycache__" in str(path) or "/patches/" in str(path):
                continue
            if is_test_file(rel(str(path))):
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                    "apex.patches"
                ):
                    importers.append(f"{path}:{node.lineno}")
                elif isinstance(node, ast.Import):
                    importers.extend(
                        f"{path}:{node.lineno}"
                        for a in node.names
                        if a.name.startswith("apex.patches")
                    )
        self.assertEqual(importers, [], "a module outside patches/ imports a patch")

    def test_every_moved_seed_runs_on_install_and_on_migrate(self):
        """A seeder wired to only one of the two leaves either new sites or existing
        ones behind, and which half is missing is invisible until someone notices."""
        for dotted in MOVED_SEEDS:
            with self.subTest(seed=dotted):
                self.assertIn(dotted, hooks.after_install, "missing from after_install")
                self.assertIn(dotted, hooks.after_migrate, "missing from after_migrate")

    def test_the_framework_creates_the_roles_so_no_seeder_should(self):
        """Frappe's make_module_and_roles (frappe/core/doctype/doctype/doctype.py:1852)
        creates a Role for every role named in a shipped DocType's permissions block, at
        install time — its own docstring says so. All five Salis roles appear in shipped
        DocPerm rows, so the seeder that created them was dead code. Verified on a clean
        site; asserted here from the JSON so it stays true as DocPerms change."""
        named = set()
        for path in APP_ROOT.rglob("doctype/*/*.json"):
            if path.stem != path.parent.name:
                continue
            try:
                meta = json.loads(path.read_text())
            except ValueError:
                continue
            named.update(perm.get("role") for perm in meta.get("permissions", []))
        for role in (
            "Fleet Manager",
            "Fleet Project Manager",
            "Fleet Supervisor",
            "Government Relations Officer",
            "Driver",
        ):
            with self.subTest(role=role):
                self.assertIn(
                    role,
                    named,
                    f"{role} is in no shipped DocPerm row, so nothing creates it on install",
                )

    def test_the_portal_role_loses_desk_access(self):
        """The one thing the framework gets wrong, and the fixture that corrects it.

        make_module_and_roles (frappe/core/doctype/doctype/doctype.py:1876-1882) inserts
        every role named in a permissions block with desk_access 1, and Driver is
        portal-only. A fixture wins that race for good: migrate.py:120-145 runs sync_all
        before sync_fixtures, on install and on every migrate, so the shipped role.json is
        applied after the framework's default rather than racing it.
        """
        entry = [f for f in hooks.fixtures if f.get("dt") == "Role"]
        self.assertEqual(len(entry), 1, "Role is not declared once in hooks.fixtures")
        self.assertIn(
            ["name", "in", ["Driver"]],
            entry[0]["filters"],
            "the Role fixture no longer filters to the portal-only role",
        )

        shipped = json.loads(
            (APP_ROOT / "fixtures" / "role.json").read_text(encoding="utf-8")
        )
        driver = [row for row in shipped if row["name"] == "Driver"]
        self.assertEqual(len(driver), 1, "role.json does not ship exactly one Driver row")
        self.assertEqual(driver[0]["desk_access"], 0, "the shipped Driver keeps desk access")
        self.assertFalse(
            frappe.db.get_value("Role", "Driver", "desk_access"),
            "Driver holds desk access on this site, so the fixture did not apply",
        )

    def test_the_settings_seed_fills_a_blank_field_and_leaves_a_set_one_alone(self):
        field = "alert_lead_days"
        before = frappe.db.get_single_value("Salis Settings", field)
        self.addCleanup(
            frappe.db.set_single_value, "Salis Settings", field, before
        )

        frappe.db.set_single_value("Salis Settings", field, 0)
        self.assertIn(field, seed_salis_settings(), "a blank default was not filled")
        self.assertEqual(
            frappe.db.get_single_value("Salis Settings", field), SETTINGS_DEFAULTS[field]
        )

        frappe.db.set_single_value("Salis Settings", field, 99)
        self.assertNotIn(field, seed_salis_settings(), "an operator's own value was overwritten")
        self.assertEqual(frappe.db.get_single_value("Salis Settings", field), 99)

    def test_the_portal_theme_seed_fills_a_blank_field(self):
        """The one true gap the card found: nothing else re-creates this Single, so
        before the move a retired patch would have taken the driver portal's theme with
        it."""
        # Driver Portal Theme is a SHIPPED DocType (apex/salis/doctype/driver_portal_theme),
        # so its absence is a broken migrate, not a site shape this case should politely
        # green over — it is the only case that grades the theme seed at all.
        self.assertTrue(
            frappe.db.exists("DocType", "Driver Portal Theme"),
            "Driver Portal Theme ships but is not on this site — the migrate is broken, "
            "and skipping here would hide the only test of the theme seed",
        )
        # The field and its expected value come from salis_portal_theme_seed.DEFAULTS, not
        # a hardcoded name: Driver Portal Theme ships show_brand / accent_color / brand_logo,
        # not `theme`, so a literal field name here would assert against a field that does
        # not exist. Reading from the seeder means a changed default cannot leave this
        # asserting a constant that moved.
        field, expected = next(iter(salis_portal_theme_seed.DEFAULTS.items()))
        before = frappe.db.get_single_value("Driver Portal Theme", field)
        self.addCleanup(
            frappe.db.set_single_value, "Driver Portal Theme", field, before
        )

        frappe.db.set_single_value("Driver Portal Theme", field, 0)
        self.assertIn(field, seed_salis_portal_theme())
        self.assertEqual(
            frappe.db.get_single_value("Driver Portal Theme", field), expected
        )
