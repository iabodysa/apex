# Copyright (c) 2026, afmcoltd

"""What a fresh install receives, an upgraded site must receive too.

Every case here guards one delivery mechanism that reaches an INSTALL and not a MIGRATE,
or one that reaches a migrate and overwrites what an operator did. Both failures are
silent by construction — nothing errors, nothing is logged, and the site simply differs
from a fresh one — which is why they are asserted from the declarations rather than
observed from a run.
"""

import ast
import json
import pathlib

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup.app_owned_permissions_seed import (
    APP_OWNED_PERMISSIONS,
    seed_app_owned_permissions,
)
from apex.apex_core.setup.workflow_names import WORKFLOWS

APP_ROOT = pathlib.Path(frappe.get_app_path("apex"))
CUSTOMISED = ("employee", "cost_center", "project")


def _hooks_list(name):
    """One hook list read from the source, so a test cannot be fooled by a live cache."""
    tree = ast.parse((APP_ROOT / "hooks.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in hooks.py")


class TestSeedersReachAnUpgradedSite(FrappeTestCase):
    """A seeder wired only to after_install never reaches a site that already exists."""

    def test_the_two_hook_seeders_run_at_migrate_as_well(self):
        after_migrate = _hooks_list("after_migrate")
        for path in (
            "apex.apex_core.setup.salis_support.grant_issue_role_permissions",
            "apex.apex_core.setup.employee_advance_recovery.seed_recovery_component",
        ):
            with self.subTest(path=path):
                self.assertIn(path, after_migrate)

    def test_the_four_master_seeders_run_at_migrate_as_well(self):
        from apex import setup

        source = ast.unparse(
            ast.parse(pathlib.Path(setup.__file__).read_text())
        )
        migrate_body = source.split("def after_migrate")[1].split("\ndef ")[0]
        for call in (
            "create_custody_asset_categories()",
            "create_custody_articles()",
            "create_operational_depreciation_policies()",
            "seed_templates()",
        ):
            with self.subTest(call=call):
                self.assertIn(call, migrate_body)


class TestShippedWorkflowsRefuseAnEdit(FrappeTestCase):
    """A fixture reimport rewrites a workflow whole, so an edit must refuse loudly."""

    def test_all_three_workflow_doctypes_are_wired(self):
        events = _hooks_list("doc_events")
        for doctype in ("Workflow", "Workflow Document State", "Workflow Transition"):
            with self.subTest(doctype=doctype):
                self.assertIn(doctype, events)

    def test_a_shipped_workflow_is_refused(self):
        from apex.apex_core.setup.app_owned_workflows import refuse_shipped_workflow_edit

        shipped = sorted(WORKFLOWS)[0]
        with self.assertRaises(frappe.PermissionError):
            refuse_shipped_workflow_edit(frappe._dict(doctype="Workflow", name=shipped))

    def test_an_operator_workflow_is_untouched(self):
        """The positive control: a refusal that refuses everything is not a gate."""
        from apex.apex_core.setup.app_owned_workflows import refuse_shipped_workflow_edit

        refuse_shipped_workflow_edit(
            frappe._dict(doctype="Workflow", name="Some Operator Workflow")
        )

    def test_a_child_row_is_refused_through_its_parent(self):
        from apex.apex_core.setup.app_owned_workflows import refuse_shipped_workflow_edit

        shipped = sorted(WORKFLOWS)[0]
        with self.assertRaises(frappe.PermissionError):
            refuse_shipped_workflow_edit(
                frappe._dict(doctype="Workflow Transition", parent=shipped, name="row1")
            )

    def test_the_fixture_import_is_not_refused(self):
        """The app's own reimport must land, or migrate refuses itself."""
        from apex.apex_core.setup.app_owned_workflows import refuse_shipped_workflow_edit

        shipped = sorted(WORKFLOWS)[0]
        frappe.flags.in_migrate = True
        try:
            refuse_shipped_workflow_edit(frappe._dict(doctype="Workflow", name=shipped))
        finally:
            frappe.flags.in_migrate = False


class TestNoInertWorkflowFilesRemain(FrappeTestCase):
    """A module-folder workflow JSON is read by nothing and silently ignores an edit."""

    def test_the_module_folders_hold_no_workflow_json(self):
        self.assertEqual(list(APP_ROOT.rglob("*/workflow/*/*.json")), [])

    def test_every_shipped_workflow_still_travels_as_a_fixture(self):
        fixture = json.loads((APP_ROOT / "fixtures" / "workflow.json").read_text())
        names = {w.get("name") or w.get("workflow_name") for w in fixture}
        self.assertEqual(set(WORKFLOWS) - names, set())


class TestAppOwnedPermissionsAreSeededNotShipped(FrappeTestCase):
    """A custom_perms block is deleted and reinserted whole on every migrate."""

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
        """The trap: ``add_permission`` defaults to read, and twelve of these must not.

        A select-only grant lets a supervisor pick an Employee in a Link field without
        being able to open the record. Seeding them with the default would hand twelve
        roles read access to personnel, cost and project data they cannot see today.
        """
        select_only = [
            (dt, role)
            for dt, role, _lvl, granted in APP_OWNED_PERMISSIONS
            if granted == ("select",)
        ]
        self.assertEqual(len(select_only), 12)
        for dt, role, _lvl, granted in APP_OWNED_PERMISSIONS:
            with self.subTest(doctype=dt, role=role):
                if granted == ("select",):
                    self.assertNotIn("read", granted)

    def test_the_seeder_is_idempotent(self):
        """It runs on every migrate, so a second call must change nothing."""
        seed_app_owned_permissions()
        before = frappe.db.count("Custom DocPerm")
        seed_app_owned_permissions()
        self.assertEqual(frappe.db.count("Custom DocPerm"), before)

    def test_the_base_roles_survive_the_dropped_block(self):
        """Asserted directly, because counting apex rows proves nothing about this.

        Custom DocPerm is all-or-nothing per DocType (frappe/model/meta.py:552), so the
        question is whether a role that exists ONLY in the base DocPerm still resolves.
        """
        roles = {p.role for p in frappe.get_meta("Employee").permissions}
        self.assertIn("HR Manager", roles)


class TestModuleDefsReachAnUpgradedSite(FrappeTestCase):
    """``add_module_defs`` is called from install_app only, never from migrate."""

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
