"""Wiring guards for the Habitat owner-scoped Maintenance Request hooks.

These are pure-Python tests (no live Frappe site required): they import the
`apex_habitat.hooks` module — which declares no top-level `import frappe`, so it
loads without a bench — and assert the registration dicts and the fixtures Role
filter are wired exactly as the owner-scoping design requires.

What they lock in:

  1. `permission_query_conditions["Maintenance Request"]` points at the Habitat
     module's `maintenance_request_query` (not the Salis module, and not the
     `before_save` controller hook that lives in `doc_events`).
  2. `has_permission["Maintenance Request"]` points at the Habitat module's
     `maintenance_request_has_permission`.
  3. Both referenced functions actually exist in
     `apex_habitat.habitat.permissions` (so a typo in the dotted path is caught
     here, not at runtime on a customer site).
  4. A complementary Role fixture exports exactly the four new operational roles,
     mirroring the existing Salis-roles fixture line, without clobbering the
     existing Habitat-roles fixture or any ERPNext/HRMS-owned role.
  5. The `Maintenance Request` `before_save` controller hook in `doc_events` is
     left intact (the new scoping wiring is additive, never a replacement).

Run standalone:  python3 -m unittest tests.test_habitat_permission_hooks -v
"""

import unittest


class TestMaintenanceRequestScopingWiring(unittest.TestCase):
    """permission_query_conditions / has_permission entries for the owner-scope."""

    QUERY_FN = "apex_habitat.habitat.permissions.maintenance_request_query"
    HAS_PERM_FN = "apex_habitat.habitat.permissions.maintenance_request_has_permission"

    def setUp(self):
        import apex_habitat.hooks as hooks

        self.hooks = hooks

    def test_permission_query_conditions_wired(self):
        self.assertEqual(
            self.hooks.permission_query_conditions.get("Maintenance Request"),
            self.QUERY_FN,
        )

    def test_has_permission_wired(self):
        self.assertEqual(
            self.hooks.has_permission.get("Maintenance Request"),
            self.HAS_PERM_FN,
        )

    def test_query_target_is_importable(self):
        from apex_habitat.habitat.permissions import maintenance_request_query

        self.assertTrue(callable(maintenance_request_query))

    def test_has_permission_target_is_importable(self):
        from apex_habitat.habitat.permissions import (
            maintenance_request_has_permission,
        )

        self.assertTrue(callable(maintenance_request_has_permission))

    def test_doc_events_before_save_left_intact(self):
        # [#l5c86z]
        self.assertEqual(
            self.hooks.doc_events["Maintenance Request"]["before_save"],
            "apex_habitat.habitat.doctype.maintenance_request."
            "maintenance_request.before_save",
        )


class TestNewRoleFixture(unittest.TestCase):
    """The complementary Role fixture exporting the four new operational roles."""

    NEW_ROLES = {
        "Maintenance Technician",
        "Cleaning Supervisor",
        "Safety Officer",
        "Resident Request Coordinator",
    }
    EXISTING_HABITAT_ROLES = {
        "Accommodation Manager",
        "Resident Supervisor",
        "Finance Manager",
        "Internal Auditor",
    }

    def setUp(self):
        import apex_habitat.hooks as hooks

        self.fixtures = hooks.fixtures

    def _role_filter_sets(self):
        """Return the list of role-name sets, one per Role fixture entry."""
        sets = []
        for entry in self.fixtures:
            if not (isinstance(entry, dict) and entry.get("dt") == "Role"):
                continue
            for flt in entry.get("filters", []) or []:
                # [#hiejf5]
                if (
                    isinstance(flt, (list, tuple))
                    and len(flt) == 3
                    and flt[0] == "name"
                    and flt[1] == "in"
                ):
                    sets.append(set(flt[2]))
        return sets

    def test_new_roles_fixture_present(self):
        sets = self._role_filter_sets()
        self.assertIn(
            self.NEW_ROLES,
            sets,
            "no Role fixture exports exactly the four new operational roles",
        )

    def test_existing_habitat_roles_fixture_untouched(self):
        sets = self._role_filter_sets()
        self.assertIn(
            self.EXISTING_HABITAT_ROLES,
            sets,
            "the existing Habitat-roles fixture must remain unchanged",
        )

    def test_new_role_fixture_is_complementary_not_merged(self):
        # [#j4kye3]
        sets = self._role_filter_sets()
        self.assertNotIn(
            self.NEW_ROLES | self.EXISTING_HABITAT_ROLES,
            sets,
            "new roles must be a separate fixture entry, not merged with the "
            "existing Habitat roles",
        )

    def test_no_new_role_clobbers_a_native_role(self):
        # [#175v0x]
        native = {
            "Employee",
            "HR Manager",
            "HR User",
            "Stock Manager",
            "Purchase Manager",
            "Accounts Manager",
            "Projects Manager",
        }
        self.assertEqual(self.NEW_ROLES & native, set())


if __name__ == "__main__":
    unittest.main()
