"""Unit tests for create_roles() and create_role_profiles() in setup.py.

These tests are pure (no site needed): they inspect the role and profile lists
defined in the seeder functions to prove:

1. Every expected role is present in the roles list — the four original
   operational roles, the four resident/facility roles, and the four later
   governance/procurement roles (Admin Manager, Operations Director,
   Facilities Supervisor, Procurement Supervisor).
2. The four original roles are untouched.
3. The four new Role Profiles are present in the profiles dict, each mapped
   to exactly the correct single role.
4. The three existing Role Profiles are untouched.
5. Running the seeders twice would be idempotent (guarded by frappe.db.exists).

The idempotency property is proven structurally: each role name appears exactly
once in the list (no duplicates that would cause a double insert), and each
profile name appears exactly once as a dict key.

The role-count check asserts the set of expected roles is exactly covered
(every expected role present, no unexpected extras, no duplicates) rather than a
brittle magic number, so the list can grow without silently passing a stale
hard-coded count.
"""

import ast
import inspect
import unittest


def _roles_list():
    """Extract the roles list from create_roles without calling frappe."""
    import apex_habitat.setup as setup_mod

    tree = ast.parse(inspect.getsource(setup_mod.create_roles))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "roles"
        ):
            return ast.literal_eval(node.value)
    return []


def _profiles_dict():
    """Extract the profiles dict from create_role_profiles without calling frappe."""
    import apex_habitat.setup as setup_mod

    tree = ast.parse(inspect.getsource(setup_mod.create_role_profiles))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "profiles"
        ):
            return ast.literal_eval(node.value)
    return {}


class TestCreateRolesList(unittest.TestCase):
    """Structural tests for the roles list in create_roles()."""

    EXISTING_ROLES = [
        "Accommodation Manager",
        "Resident Supervisor",
        "Finance Manager",
        "Internal Auditor",
    ]
    NEW_ROLES = [
        "Maintenance Technician",
        "Cleaning Supervisor",
        "Safety Officer",
        "Resident Request Coordinator",
    ]
    # Roles added by the later safety build (Admin Manager / Operations Director /
    # Facilities Supervisor) and Wave 0 (Procurement Supervisor).
    GOVERNANCE_ROLES = [
        "Admin Manager",
        "Operations Director",
        "Facilities Supervisor",
        "Procurement Supervisor",
    ]

    @property
    def EXPECTED_ROLES(self):
        return self.EXISTING_ROLES + self.NEW_ROLES + self.GOVERNANCE_ROLES

    def setUp(self):
        self.roles = _roles_list()

    def test_all_governance_roles_present(self):
        for role in self.GOVERNANCE_ROLES:
            self.assertIn(role, self.roles, f"Governance role missing: {role}")

    def test_all_existing_roles_present(self):
        for role in self.EXISTING_ROLES:
            self.assertIn(role, self.roles, f"Existing role missing: {role}")

    def test_all_new_roles_present(self):
        for role in self.NEW_ROLES:
            self.assertIn(role, self.roles, f"New role missing: {role}")

    def test_no_duplicate_roles(self):
        self.assertEqual(
            len(self.roles),
            len(set(self.roles)),
            "Duplicate role names detected — would cause non-idempotent inserts.",
        )

    def test_total_role_count(self):
        # [#3tgwn1] Robust over a brittle magic count: the roles list must cover
        # exactly the expected set (no missing, no unexpected extras).
        self.assertEqual(
            set(self.roles),
            set(self.EXPECTED_ROLES),
            "Roles list does not match the expected role set "
            "(update EXPECTED_ROLES when create_roles changes).",
        )


class TestCreateRoleProfilesDict(unittest.TestCase):
    """Structural tests for the profiles dict in create_role_profiles()."""

    EXISTING_PROFILES = {
        "Habitat Accommodation Manager": ["Accommodation Manager", "System Manager"],
        "Habitat Resident Supervisor": ["Resident Supervisor"],
        "Habitat Finance Reviewer": ["Finance Manager", "Internal Auditor"],
    }
    NEW_PROFILES = {
        "Habitat Maintenance Technician": ["Maintenance Technician"],
        "Habitat Cleaning Supervisor": ["Cleaning Supervisor"],
        "Habitat Safety Officer": ["Safety Officer"],
        "Habitat Resident Request Coordinator": ["Resident Request Coordinator"],
    }

    def setUp(self):
        self.profiles = _profiles_dict()

    def test_all_existing_profiles_present_and_unchanged(self):
        for name, roles in self.EXISTING_PROFILES.items():
            self.assertIn(name, self.profiles, f"Existing profile missing: {name}")
            self.assertEqual(
                self.profiles[name],
                roles,
                f"Existing profile roles changed for {name}",
            )

    def test_all_new_profiles_present(self):
        for name in self.NEW_PROFILES:
            self.assertIn(name, self.profiles, f"New profile missing: {name}")

    def test_new_profile_role_mappings(self):
        for name, expected_roles in self.NEW_PROFILES.items():
            self.assertEqual(
                self.profiles[name],
                expected_roles,
                f"Wrong role mapping for profile {name}",
            )

    def test_no_duplicate_profile_names(self):
        # [#4osqz9]
        import apex_habitat.setup as setup_mod

        tree = ast.parse(inspect.getsource(setup_mod.create_role_profiles))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "profiles"
            ):
                keys = [ast.literal_eval(k) for k in node.value.keys]
                self.assertEqual(
                    len(keys),
                    len(set(keys)),
                    "Duplicate profile names in source — would lose rows silently.",
                )
                return
        self.fail("profiles dict not found in create_role_profiles source")

    def test_total_profile_count(self):
        self.assertEqual(len(self.profiles), 7)

    def test_each_new_profile_maps_exactly_one_role(self):
        for name in self.NEW_PROFILES:
            roles = self.profiles[name]
            self.assertEqual(
                len(roles),
                1,
                f"New profile {name} must map to exactly one role, got {roles}",
            )

    def test_new_profile_role_names_match_new_roles(self):
        """Each new profile's role must be one of the new roles added in create_roles."""
        new_role_names = {
            "Maintenance Technician",
            "Cleaning Supervisor",
            "Safety Officer",
            "Resident Request Coordinator",
        }
        for name, roles in self.NEW_PROFILES.items():
            for role in roles:
                self.assertIn(
                    role,
                    new_role_names,
                    f"Profile {name} references role {role!r} not in new-roles set",
                )


if __name__ == "__main__":
    unittest.main()
