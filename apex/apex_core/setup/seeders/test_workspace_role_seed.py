# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Workspace-role seeder.

Restricts every roleless public Workspace to the roles that can actually read the
doctypes/reports it links to, so a Workspace nobody scoped is not silently visible
to every role. Exercised against a throwaway Workspace linking a real Apex DocType
(Building) whose DocPerm read-roles are known and stable, so the expected role set
can be asserted exactly rather than just "non-empty".
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup.seeders.workspace_role_seed import (
    EXCLUDED_ROLES,
    seed_workspace_roles,
)

# Building's DocPerm read-roles (habitat/doctype/building/building.json), all
# permlevel 0, if_owner 0 -- the exact set the seeder should derive.
_BUILDING_READ_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Resident Supervisor",
    "Safety Officer",
}


class TestWorkspaceRoleSeed(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.ws_name = f"A564 Role Seed Test {frappe.generate_hash(length=8)}"
        ws = frappe.get_doc(
            {
                "doctype": "Workspace",
                "name": self.ws_name,
                "label": self.ws_name,
                "title": self.ws_name,
                "public": 1,
                "module": "Apex Core",
                "content": "[]",
                "links": [
                    {
                        "type": "Link",
                        "label": "Building",
                        "link_type": "DocType",
                        "link_to": "Building",
                    }
                ],
            }
        )
        ws.flags.ignore_permissions = True
        ws.flags.ignore_links = True
        ws.insert()
        self.addCleanup(self._delete_ws)

    def _delete_ws(self):
        frappe.delete_doc("Workspace", self.ws_name, force=True, ignore_permissions=True)

    def _reload(self):
        return frappe.get_doc("Workspace", self.ws_name)

    def test_a_roleless_workspace_is_restricted_to_exactly_the_linked_doctypes_read_roles(self):
        seed_workspace_roles()
        roles = {r.role for r in self._reload().roles}
        self.assertEqual(roles, _BUILDING_READ_ROLES)

    def test_no_assigned_role_is_ever_from_the_excluded_set(self):
        seed_workspace_roles()
        roles = {r.role for r in self._reload().roles}
        self.assertTrue(roles.isdisjoint(EXCLUDED_ROLES))

    def test_a_workspace_that_already_has_a_role_is_left_alone(self):
        ws = self._reload()
        ws.append("roles", {"role": "System Manager"})
        ws.flags.ignore_permissions = True
        ws.save()

        seed_workspace_roles()

        roles = {r.role for r in self._reload().roles}
        self.assertEqual(roles, {"System Manager"}, "an already-scoped workspace must not be touched")
