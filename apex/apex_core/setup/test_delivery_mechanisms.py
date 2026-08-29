# Copyright (c) 2026, afmcoltd


import ast
import json
import pathlib

import frappe
from frappe.tests.utils import FrappeTestCase

from apex import setup
from apex.apex_core.setup.app_owned_permissions_seed import (
    APP_OWNED_PERMISSIONS,
    seed_app_owned_permissions,
)
from apex.apex_core.setup.app_owned_workflows import refuse_shipped_workflow_edit
from apex.apex_core.setup.workflow_names import WORKFLOWS
from apex.patches.v2_9 import prune_orphaned_number_cards

APP_ROOT = pathlib.Path(frappe.get_app_path("apex"))
CUSTOMISED = ("employee", "cost_center", "project")


def _hooks_list(name):
    tree = ast.parse((APP_ROOT / "hooks.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in hooks.py")


class TestSeedersReachAnUpgradedSite(FrappeTestCase):

    def test_the_two_hook_seeders_run_at_migrate_as_well(self):
        after_migrate = _hooks_list("after_migrate")
        for path in (
            "apex.apex_core.setup.salis_support.grant_issue_role_permissions",
            "apex.apex_core.setup.employee_advance_recovery.seed_recovery_component",
        ):
            with self.subTest(path=path):
                self.assertIn(path, after_migrate)

    def test_the_remaining_master_seeder_runs_at_migrate_as_well(self):
        source = ast.unparse(
            ast.parse(pathlib.Path(setup.__file__).read_text())
        )
        migrate_body = source.split("def after_migrate")[1].split("\ndef ")[0]
        self.assertIn("seed_templates()", migrate_body)


class TestCustodyMastersShipAsFixtures(FrappeTestCase):

    def test_no_seeder_creates_the_three_masters(self):
        source = pathlib.Path(
            __import__("apex.setup", fromlist=["setup"]).__file__
        ).read_text()
        for name in (
            "create_custody_asset_categories",
            "create_custody_articles",
            "create_operational_depreciation_policies",
        ):
            with self.subTest(name=name):
                self.assertNotIn(name, source)

    def test_every_fixture_row_matches_the_shipped_file(self):
        for dt, fixture_file in (
            ("Custody Asset Category", "custody_asset_category.json"),
            ("Custody Article", "custody_article.json"),
            ("Operational Depreciation Policy", "operational_depreciation_policy.json"),
            ("Safety Task Catalog", "safety_task_catalog.json"),
            ("Role Profile", "role_profile.json"),
        ):
            with self.subTest(doctype=dt):
                shipped = json.loads((APP_ROOT / "fixtures" / fixture_file).read_text())
                names = {row["name"] for row in shipped}
                self.assertGreater(len(names), 0)
                for name in names:
                    self.assertTrue(
                        frappe.db.exists(dt, name),
                        f"{dt} {name} is fixture-declared but not on this site",
                    )


class TestRoleProfilesShipAsAFixture(FrappeTestCase):

    def test_no_seeder_creates_the_role_profiles(self):
        source = pathlib.Path(setup.__file__).read_text()
        self.assertNotIn("create_role_profiles", source)
        self.assertNotIn("create_role_profiles", (APP_ROOT / "hooks.py").read_text())

    def test_the_fixture_declares_a_role_for_every_profile(self):
        shipped = json.loads((APP_ROOT / "fixtures" / "role_profile.json").read_text())
        self.assertEqual(len(shipped), 8)
        for row in shipped:
            with self.subTest(profile=row["name"]):
                self.assertGreater(len(row["roles"]), 0)
                for child in row["roles"]:
                    self.assertTrue(frappe.db.exists("Role", child["role"]))

    def test_every_fixture_profile_is_declared_in_hooks(self):
        declared = {
            name
            for entry in frappe.get_hooks("fixtures", app_name="apex")
            if isinstance(entry, dict) and entry.get("dt") == "Role Profile"
            for condition in entry["filters"]
            for name in condition[2]
        }
        shipped = json.loads((APP_ROOT / "fixtures" / "role_profile.json").read_text())
        self.assertEqual(declared, {row["name"] for row in shipped})


class TestOrphanedNumberCardsAreSweptByAPatch(FrappeTestCase):

    def test_the_patch_is_registered(self):
        self.assertIn(
            "apex.patches.v2_9.prune_orphaned_number_cards",
            (APP_ROOT / "patches.txt").read_text(),
        )

    def test_no_hook_runs_the_sweep_on_every_migrate(self):
        self.assertNotIn("prune_number_cards", str(_hooks_list("after_migrate")))
        self.assertFalse((APP_ROOT / "apex_core" / "setup" / "prune_number_cards.py").exists())

    def test_the_sweep_removes_no_shipped_number_card(self):
        card_filters = {
            "module": ["in", prune_orphaned_number_cards.APEX_MODULES],
            "is_standard": 1,
        }
        before = frappe.get_all("Number Card", filters=card_filters, pluck="name")
        self.assertGreater(len(before), 0)

        prune_orphaned_number_cards.execute()

        after = frappe.get_all("Number Card", filters=card_filters, pluck="name")
        self.assertEqual(sorted(before), sorted(after))


class TestShippedWorkflowsRefuseAnEdit(FrappeTestCase):

    def test_all_three_workflow_doctypes_are_wired(self):
        events = _hooks_list("doc_events")
        for doctype in ("Workflow", "Workflow Document State", "Workflow Transition"):
            with self.subTest(doctype=doctype):
                self.assertIn(doctype, events)

    def test_a_shipped_workflow_is_refused(self):
        shipped = sorted(WORKFLOWS)[0]
        with self.assertRaises(frappe.PermissionError):
            refuse_shipped_workflow_edit(frappe._dict(doctype="Workflow", name=shipped))

    def test_an_operator_workflow_is_untouched(self):
        refuse_shipped_workflow_edit(
            frappe._dict(doctype="Workflow", name="Some Operator Workflow")
        )

    def test_a_child_row_is_refused_through_its_parent(self):
        shipped = sorted(WORKFLOWS)[0]
        with self.assertRaises(frappe.PermissionError):
            refuse_shipped_workflow_edit(
                frappe._dict(doctype="Workflow Transition", parent=shipped, name="row1")
            )

    def test_the_fixture_import_is_not_refused(self):
        shipped = sorted(WORKFLOWS)[0]
        frappe.flags.in_migrate = True
        try:
            refuse_shipped_workflow_edit(frappe._dict(doctype="Workflow", name=shipped))
        finally:
            frappe.flags.in_migrate = False


class TestNoInertWorkflowFilesRemain(FrappeTestCase):

    def test_the_module_folders_hold_no_workflow_json(self):
        self.assertEqual(list(APP_ROOT.rglob("*/workflow/*/*.json")), [])

    def test_every_shipped_workflow_still_travels_as_a_fixture(self):
        fixture = json.loads((APP_ROOT / "fixtures" / "workflow.json").read_text())
        names = {w.get("name") or w.get("workflow_name") for w in fixture}
        self.assertEqual(set(WORKFLOWS) - names, set())


class TestAppOwnedPermissionsAreSeededNotShipped(FrappeTestCase):

    def test_no_customisation_file_carries_custom_perms(self):
        for name in CUSTOMISED:
            with self.subTest(name=name):
                data = json.loads(
                    (APP_ROOT / "habitat" / "custom" / f"{name}.json").read_text()
                )
                self.assertNotIn("custom_perms", data)

    def test_the_seeder_runs_at_install_and_at_migrate(self):
        path = "apex.apex_core.setup.app_owned_permissions_seed.seed_app_owned_permissions"
        self.assertIn(path, _hooks_list("after_install"))
        self.assertIn(path, _hooks_list("after_migrate"))

    def test_the_select_only_rows_do_not_grant_read(self):
        select_only = [
            (dt, role)
            for dt, role, _lvl, granted in APP_OWNED_PERMISSIONS
            if granted == ("select",)
        ]
        self.assertEqual(len(select_only), 13)
        for dt, role, _lvl, granted in APP_OWNED_PERMISSIONS:
            with self.subTest(doctype=dt, role=role):
                if granted == ("select",):
                    self.assertNotIn("read", granted)

    def test_the_seeder_creates_the_rows_when_they_are_absent(self):
        frappe.db.delete("Custom DocPerm", {"parent": "Employee"})
        frappe.clear_cache(doctype="Employee")
        self.assertEqual(frappe.db.count("Custom DocPerm", {"parent": "Employee"}), 0)

        seed_app_owned_permissions()
        frappe.clear_cache(doctype="Employee")
        created = frappe.db.count("Custom DocPerm", {"parent": "Employee"})
        self.assertGreater(created, 0)

        seed_app_owned_permissions()
        self.assertEqual(
            frappe.db.count("Custom DocPerm", {"parent": "Employee"}), created
        )

    def test_a_select_only_role_is_not_granted_read_on_the_site(self):
        frappe.db.delete("Custom DocPerm", {"parent": "Employee"})
        frappe.clear_cache(doctype="Employee")
        seed_app_owned_permissions()

        row = frappe.db.get_value(
            "Custom DocPerm",
            {"parent": "Employee", "role": "Accommodation Manager", "permlevel": 0},
            ["select", "read"],
            as_dict=True,
        )
        self.assertTrue(row, "the select-only row was not created")
        self.assertEqual(row.select, 1)
        self.assertEqual(row.read, 0)

    def test_the_base_roles_survive_the_dropped_block(self):
        frappe.db.delete("Custom DocPerm", {"parent": "Employee"})
        frappe.clear_cache(doctype="Employee")

        roles = {p.role for p in frappe.get_meta("Employee").permissions}
        self.assertIn("HR Manager", roles)
        self.assertIn("HR User", roles)


class TestModuleDefsReachAnUpgradedSite(FrappeTestCase):

    def test_the_patch_is_registered(self):
        registered = (APP_ROOT / "patches.txt").read_text()
        self.assertIn("apex.patches.v2_8.insert_missing_module_defs", registered)

    def test_every_module_has_a_def_on_this_site(self):
        declared = [
            m.strip()
            for m in (APP_ROOT / "modules.txt").read_text().splitlines()
            if m.strip()
        ]
        present = frappe.get_all("Module Def", filters={"app_name": "apex"}, pluck="name")
        self.assertEqual(sorted(set(declared) - set(present)), [])


class TestSeedersUnfitForAFixtureStayCode(FrappeTestCase):

    def test_none_of_the_nine_doctypes_ship_as_a_fixture_file(self):
        for doctype in (
            "Auto Email Report",
            "Module Profile",
            "Maintenance Material Template",
            "User",
            "Role",
            "Navbar Settings",
            "Salis Settings",
        ):
            with self.subTest(doctype=doctype):
                self.assertFalse(
                    (APP_ROOT / "fixtures" / f"{frappe.scrub(doctype)}.json").exists()
                )


class TestFixturesShipNaturalKeysNotCounters(FrappeTestCase):

    def _fixture_doctypes(self):
        for path in sorted((APP_ROOT / "fixtures").glob("*.json")):
            rows = json.loads(path.read_text())
            if isinstance(rows, list) and rows and rows[0].get("doctype"):
                yield path, rows[0]["doctype"], rows

    def test_no_fixture_ships_a_record_named_by_a_counter(self):
        checked = 0
        for path, doctype, rows in self._fixture_doctypes():
            autoname = frappe.get_meta(doctype).autoname or ""
            checked += 1
            with self.subTest(fixture=path.name):
                self.assertFalse(
                    autoname.startswith("naming_series:") or "#" in autoname,
                    f"{doctype} is named by a counter, which fixture import never advances",
                )
        self.assertGreater(checked, 0)

    def test_every_fixture_name_is_the_value_of_the_field_that_names_it(self):
        checked = 0
        for path, doctype, rows in self._fixture_doctypes():
            autoname = frappe.get_meta(doctype).autoname or ""
            if not autoname.startswith("field:"):
                continue
            keyfield = autoname.split(":", 1)[1]
            for row in rows:
                checked += 1
                with self.subTest(fixture=path.name, name=row["name"]):
                    self.assertEqual(row["name"], row[keyfield])
        self.assertGreater(checked, 0)

    def test_a_new_master_takes_its_natural_key_as_its_name(self):
        doc = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_title": "_T-Natural Key Probe",
                "department": "Fire Safety",
                "task_code": "_T-NATKEY-PROBE",
                "frequency": "Weekly",
            }
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.name, "_T-NATKEY-PROBE")
        frappe.delete_doc(
            "Safety Task Catalog", doc.name, ignore_permissions=True, force=True
        )

    def test_the_rename_patch_runs_before_the_model_sync(self):
        # Model sync builds the unique index on the natural-key field, so a row
        # still carrying its counter name has to be renamed before sync, not after.
        sections = (APP_ROOT / "patches.txt").read_text().split("[post_model_sync]")
        self.assertEqual(len(sections), 2)
        self.assertIn(
            "apex.patches.v2_10.rename_fixture_masters_to_their_natural_key",
            sections[0],
        )
