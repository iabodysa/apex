# Copyright (c) 2026, afmcoltd


import json
import pathlib

import frappe
from frappe.tests.utils import FrappeTestCase

APP_ROOT = pathlib.Path(frappe.get_app_path("apex"))


def _shipped_workspaces():
    found = {}
    for path in APP_ROOT.rglob("workspace/*/*.json"):
        data = json.loads(path.read_text())
        if data.get("doctype") == "Workspace" and data.get("public"):
            found[data["name"]] = data
    return found


class TestTheFileIsTheSourceOfTruth(FrappeTestCase):
    def test_no_seeder_derives_workspace_roles(self):
        offenders = [
            str(p)
            for p in APP_ROOT.rglob("*.py")
            if not p.name.startswith("test_") and "seed_workspace_roles" in p.read_text()
        ]
        self.assertEqual(offenders, [])

    def test_every_shipped_workspace_matches_its_file_on_this_site(self):
        for name, data in _shipped_workspaces().items():
            with self.subTest(workspace=name):
                if not frappe.db.exists("Workspace", name):
                    continue
                declared = {r["role"] for r in (data.get("roles") or [])}
                live = {
                    r.role for r in frappe.get_doc("Workspace", name).roles
                }
                self.assertEqual(
                    live - declared,
                    set(),
                    f"{name} carries a role no file declares",
                )

    def test_the_personal_queue_is_open_to_every_desk_user(self):
        data = _shipped_workspaces().get("My Tasks")
        self.assertIsNotNone(data, "My Tasks is no longer shipped")
        self.assertEqual(data.get("roles") or [], [])
        if frappe.db.exists("Workspace", "My Tasks"):
            self.assertEqual(len(frappe.get_doc("Workspace", "My Tasks").roles), 0)

    def test_a_restricted_workspace_still_declares_its_own_audience(self):
        declared = {
            name: len(data.get("roles") or [])
            for name, data in _shipped_workspaces().items()
        }
        self.assertGreater(
            sum(1 for count in declared.values() if count), 0, declared
        )
