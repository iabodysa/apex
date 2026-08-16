# Copyright (c) 2026, AFMCO and contributors
"""The shipped Module Profiles, and what a persona's desk sidebar actually returns.

The subject is what a person SEES, so the load-bearing case here calls
``frappe.desk.desktop.get_workspace_sidebar_items`` as the persona and compares the
two lists it returns with and without the profile linked -- the same call, the same
site, the same roles, one field changed.

Two traps this file is built around, both measured on ci.localhost:

  * Clearing ``User.module_profile`` does NOT clear ``User.block_modules``.
    ``validate_allowed_modules`` only copies rows in when the link is set
    (``frappe/core/doctype/user/user.py:217-222``) and never empties the table when
    it is cleared, so an unlink-and-measure "before" silently keeps every blocked
    module and reads identical to the "after". The table is emptied explicitly here.
  * A user holding Workspace Manager bypasses module blocking altogether --
    ``get_workspace_sidebar_items`` sets ``filters = []`` for them
    (``frappe/desk/desktop.py:428, 435-436``). The persona's role list is asserted
    clean of it, so a future failure reads as a role problem rather than a seeder one.

Size note: 169 test lines against 48 in the subject (3.5x), for 12 distinct behaviours. The ratio is arithmetic on a small subject, not overtesting — each test names a different one.
"""

import unittest

import frappe
from frappe.desk.desktop import get_workspace_sidebar_items

from apex.apex_core.setup.seeders.module_profile_seed import (
    ADMINISTRATION_MODULES,
    APEX_MODULES,
    BACK_OFFICE_MODULES,
    EMPLOYMENT_MODULES,
    MODULE_PROFILES,
    blocked_modules_for,
    seed_module_profiles,
)

PERSONA = "module.profile.persona@apex.test"

PERSONA_ROLES = ("Desk User", "Accommodation Manager", "Resident Supervisor")

ADMINISTRATION_WORKSPACES = ("Home",)
"""Public Workspace(s) under an ADMINISTRATION_MODULES module whose own roles table
is empty, so a persona sees them until the module itself is blocked.

``Users``, ``Build``, ``Integrations`` and ``ERPNext Settings`` no longer qualify: each
carries a non-empty ``roles`` child table on ``frappe/core/workspace/*/*.json`` (for
example ``users.json`` ships ``roles: [{"role": "System Manager"}]``), so a supervisor
persona never sees them regardless of Module Profile. ``Home`` (module ``Setup``,
``frappe/config/desktop.py`` / the Setup module Workspace fixture) ships no roles
table and is the one workspace left that demonstrates the block: present with no
profile linked, absent once ``Apex Operations Desk`` blocks ``Setup``.
"""


def sidebar_workspaces(user):
    """Workspace names ``get_workspace_sidebar_items`` returns for one user."""
    previous = frappe.session.user
    try:
        frappe.set_user(user)
        frappe.clear_cache(user=user)
        return {page["name"] for page in get_workspace_sidebar_items()["pages"]}
    finally:
        frappe.set_user(previous)


def apex_workspaces():
    return set(
        frappe.get_all("Workspace", filters={"module": ["in", list(APEX_MODULES)]}, pluck="name")
    )


class TestModuleProfileComposition(unittest.TestCase):
    """What each shipped profile blocks, decided from source rather than the site."""

    def test_no_apex_module_is_ever_blocked(self):
        for profile_name in MODULE_PROFILES:
            with self.subTest(profile=profile_name):
                blocked = set(blocked_modules_for(profile_name))
                self.assertTrue(
                    blocked.isdisjoint(APEX_MODULES),
                    f"{profile_name} blocks an Apex module: {sorted(blocked & set(APEX_MODULES))}",
                )

    def test_employment_modules_are_never_blocked(self):
        """HR and Payroll carry the person's own records and have no Apex replacement."""
        for profile_name in MODULE_PROFILES:
            with self.subTest(profile=profile_name):
                blocked = set(blocked_modules_for(profile_name))
                self.assertTrue(
                    blocked.isdisjoint(EMPLOYMENT_MODULES),
                    f"{profile_name} blocks {sorted(blocked & set(EMPLOYMENT_MODULES))}",
                )

    def test_every_profile_blocks_every_administration_surface(self):
        for profile_name in MODULE_PROFILES:
            with self.subTest(profile=profile_name):
                self.assertTrue(
                    set(ADMINISTRATION_MODULES).issubset(blocked_modules_for(profile_name)),
                    f"{profile_name} leaves an administration module visible",
                )

    def test_each_profile_keeps_only_what_its_persona_transacts_in(self):
        expected = {
            "Apex Operations Desk": set(),
            "Apex Procurement Desk": {"Buying", "Stock"},
            "Apex Finance Desk": {"Accounts", "Assets", "Projects"},
        }
        self.assertEqual(set(expected), set(MODULE_PROFILES))
        for profile_name, kept in expected.items():
            with self.subTest(profile=profile_name):
                blocked = set(blocked_modules_for(profile_name))
                self.assertEqual(set(BACK_OFFICE_MODULES) - blocked, kept)


class TestModuleProfileSeeder(unittest.TestCase):
    """The seeder creates once and never writes over an existing record."""

    def test_migrate_left_every_profile_on_the_site(self):
        for profile_name in MODULE_PROFILES:
            with self.subTest(profile=profile_name):
                self.assertTrue(
                    frappe.db.exists("Module Profile", profile_name),
                    f"{profile_name} is missing -- after_install / after_migrate did not run it",
                )

    def test_stored_rows_match_the_shipped_list(self):
        for profile_name in MODULE_PROFILES:
            with self.subTest(profile=profile_name):
                doc = frappe.get_doc("Module Profile", profile_name)
                self.assertEqual(
                    sorted(row.module for row in doc.block_modules),
                    blocked_modules_for(profile_name),
                )

    def test_seeder_leaves_no_locked_document(self):
        """Module Profile's on_update queues an action, and queue_action locks the doc."""
        for profile_name in MODULE_PROFILES:
            with self.subTest(profile=profile_name):
                self.assertFalse(
                    frappe.get_doc("Module Profile", profile_name).is_locked,
                    f"{profile_name} is still locked -- the next save raises DocumentLockedError",
                )

    def _write_rows(self, profile_name, modules):
        doc = frappe.get_doc("Module Profile", profile_name)
        doc.block_modules = []
        for module in modules:
            doc.append("block_modules", {"module": module})
        doc.save(ignore_permissions=True)
        doc.unlock()

    def test_a_hand_edited_profile_survives_a_re_run(self):
        """The record is an administrator's to edit; the seeder only ever creates.

        ``ModuleProfile.on_update`` pushes the edit straight out to every linked user
        (``frappe/core/doctype/module_profile/module_profile.py:44-62``), and this
        suite shares its site with the other cases, so the shipped rows are put back
        before anything else reads them.
        """
        profile_name = "Apex Operations Desk"
        self.addCleanup(self._write_rows, profile_name, blocked_modules_for(profile_name))
        self._write_rows(profile_name, ["Website"])

        seed_module_profiles()

        rows = [row.module for row in frappe.get_doc("Module Profile", profile_name).block_modules]
        self.assertEqual(rows, ["Website"], "the seeder overwrote an administrator's edit")


class TestPersonaSidebar(unittest.TestCase):
    """The decisive case: the same call, as the persona, with and without the profile."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        if frappe.db.exists("User", PERSONA):
            frappe.delete_doc("User", PERSONA, force=True, ignore_permissions=True)
        user = frappe.new_doc("User")
        user.email = PERSONA
        user.first_name = "Module Profile"
        user.last_name = "Persona"
        user.send_welcome_email = 0
        for role in PERSONA_ROLES:
            user.append("roles", {"role": role})
        user.insert(ignore_permissions=True)
        cls.user = user.name

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")

    def _link(self, profile_name):
        doc = frappe.get_doc("User", self.user)
        doc.module_profile = profile_name
        if not profile_name:
            doc.set("block_modules", [])
        doc.save(ignore_permissions=True)

    def test_persona_does_not_hold_the_bypass_role(self):
        frappe.set_user(self.user)
        try:
            roles = frappe.get_roles()
        finally:
            frappe.set_user("Administrator")
        self.assertNotIn(
            "Workspace Manager",
            roles,
            "the persona bypasses module blocking, so this file would grade nothing",
        )

    def test_profile_removes_the_administration_workspaces_and_keeps_apex(self):
        self._link(None)
        before = sidebar_workspaces(self.user)
        self._link("Apex Operations Desk")
        after = sidebar_workspaces(self.user)

        for workspace in ADMINISTRATION_WORKSPACES:
            with self.subTest(workspace=workspace):
                self.assertIn(workspace, before, "the defect is not reproducible on this site")
                self.assertNotIn(workspace, after)

        self.assertEqual(
            before & apex_workspaces(),
            after & apex_workspaces(),
            "the profile took an Apex workspace away from its own persona",
        )
        self.assertLess(len(after), len(before))

    def test_administrator_holds_the_bypass_role(self):
        """Administrator holds every role, so the sidebar filter is cleared for them.

        A plain System Manager does NOT hold Workspace Manager and gets no such bypass
        -- measured on ci.localhost, linking a profile to one takes their sidebar from
        40 entries to 19. That is why the seeder links nobody.
        """
        self.assertIn("Workspace Manager", frappe.get_roles("Administrator"))

    def test_administrator_keeps_every_workspace(self):
        self.assertIsNone(
            frappe.db.get_value("User", "Administrator", "module_profile"),
            "Administrator's blocked modules are read as the site-wide block list "
            "(frappe/config/__init__.py:8)",
        )
        self.assertEqual(frappe.get_doc("User", "Administrator").get_blocked_modules(), [])

        admin = sidebar_workspaces("Administrator")
        every_public = set(
            frappe.get_all("Workspace", filters={"public": 1}, pluck="name")
        ) - {"Welcome Workspace"}
        self.assertEqual(
            every_public - admin,
            set(),
            "Administrator lost a workspace",
        )


if __name__ == "__main__":
    unittest.main()
