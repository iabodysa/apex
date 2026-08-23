# Copyright (c) 2026, afmcoltd

"""A Workspace's audience comes from its own file, never from a derivation.

Workspace sits in ``IMPORTABLE_DOCTYPES`` (frappe/model/sync.py:17-37), so ``sync_all``
ships each one from its JSON on install and on every migrate. A seeder that derives the
audience instead cannot be read from the repository: the file says one thing and the site
says another, with nothing to explain the gap.

The derivation that was retired kept only DocPerm rows with ``if_owner: 0``. A PERSONAL
workspace rests on the opposite rule — a person sees their own rows — so the derivation
was blind to exactly the permission that makes it personal, concluded that nobody could
see it, and restricted the personal task queue to System Manager.
"""

import json
import pathlib

import frappe
from frappe.tests.utils import FrappeTestCase

APP_ROOT = pathlib.Path(frappe.get_app_path("apex"))


def _shipped_workspaces():
    """Every public Workspace this app ships, read from the files themselves."""
    found = {}
    for path in APP_ROOT.rglob("workspace/*/*.json"):
        data = json.loads(path.read_text())
        if data.get("doctype") == "Workspace" and data.get("public"):
            found[data["name"]] = data
    return found


class TestTheFileIsTheSourceOfTruth(FrappeTestCase):
    def test_no_seeder_derives_workspace_roles(self):
        """The retired module must not come back under any name."""
        offenders = [
            str(p)
            for p in APP_ROOT.rglob("*.py")
            if not p.name.startswith("test_") and "seed_workspace_roles" in p.read_text()
        ]
        self.assertEqual(offenders, [])

    def test_every_shipped_workspace_matches_its_file_on_this_site(self):
        """The gap this closes: a role row on the site that no file declares."""
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
        """A personal workspace restricted to one role costs every other operator
        their own task list, and an empty roles array is what says 'anyone'."""
        data = _shipped_workspaces().get("My Tasks")
        self.assertIsNotNone(data, "My Tasks is no longer shipped")
        self.assertEqual(data.get("roles") or [], [])
        if frappe.db.exists("Workspace", "My Tasks"):
            self.assertEqual(len(frappe.get_doc("Workspace", "My Tasks").roles), 0)

    def test_a_restricted_workspace_still_declares_its_own_audience(self):
        """The positive control: if every workspace came back roleless, the test
        above would pass while the estate lost every restriction it had."""
        declared = {
            name: len(data.get("roles") or [])
            for name, data in _shipped_workspaces().items()
        }
        self.assertGreater(
            sum(1 for count in declared.values() if count), 0, declared
        )
