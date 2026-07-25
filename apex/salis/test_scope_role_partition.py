# Copyright (c) 2026, AFMCO and contributors
"""A-171 — a role granted lists whose row filter can only ever return ``1=0``.

Every Salis DocType wired into ``hooks.permission_query_conditions`` gets its WHERE
fragment from ``apex.salis.permissions``. That fragment has exactly three outcomes
(``apex_core/utils/permission_scope.scope_condition``):

  * ``""``            — the user holds a role in ``UNSCOPED_ROLES``; no restriction.
  * ``project in (…)`` — the user holds Project User Permissions; rows in those projects.
  * ``1=0``            — the user is scoped and holds NO Project User Permission.

``Government Relations Officer`` was granted read DocPerms on five Salis DocTypes while
sitting in none of those buckets: it is not an oversight role, it is never issued a
Project User Permission (its charter is company-wide compliance, not a project posting),
and its DocPerm rows carry no ``if_owner`` fallback. Every list it was granted therefore
resolved to ``1=0`` and rendered zero rows — a grant that looks correct in the DocType
JSON and is empty on screen.

This guard partitions every role reading a project-scoped Salis DocType into the three
declared buckets and fails on any role in none of them. Adding a role to ``UNSCOPED_ROLES``
and adding it to a DocPerm are then forced to happen together.

File-level and stdlib-only on purpose: the invariant is a property of the shipped source
plus the shipped JSON, so it must fail on the commit that WRITES the mismatch rather than
on a site that already migrated it.

Run standalone:  python3 -m unittest apex.salis.test_scope_role_partition -v
"""

import ast
import glob
import json
import os
import unittest

_SALIS = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.normpath(os.path.join(_SALIS, ".."))
_HOOKS = os.path.join(_APP, "hooks.py")
_PERMISSIONS = os.path.join(_SALIS, "permissions.py")
_DOCTYPE_GLOB = os.path.join(_APP, "*", "doctype", "*", "*.json")

GRO_ROLE = "Government Relations Officer"

# Roles that receive a User Permission on Project, so the scoped branch returns rows for
# them. Source of truth: docs/training/README.md — "Fleet Project Managers and Supervisors
# see only their permitted projects ... Grant access via a User Permission on Project."
PROJECT_SCOPED_ROLES = {
    "Fleet Project Manager",
    "Fleet Supervisor",
}

# Roles that reach rows through the owner / own-driver clause the query ORs in, not through
# a project grant. Every DocPerm row they hold on a scoped DocType must carry if_owner.
OWNER_SCOPED_ROLES = {
    "Driver",
}

# Administrator short-circuits in permission_scope.is_unscoped before any role lookup.
_SUPERUSERS = {"Administrator"}

KNOWN_ZEROED_ROLES = {
    # Frozen baseline of role -> why a role in none of the three buckets is tolerated.
    # Empty: A-171 closed the only entry. Exact equality, so a NEW name fails the build.
}


def _literal_from_module(path, name):
    """Read a module-level literal assignment without importing the module."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found as a module-level assignment in {path}")


def unscoped_roles():
    """The oversight set bound in apex/salis/permissions.py."""
    return set(_literal_from_module(_PERMISSIONS, "UNSCOPED_ROLES"))


def scoped_doctypes():
    """DocTypes whose list query is scoped by apex.salis.permissions."""
    mapping = _literal_from_module(_HOOKS, "permission_query_conditions")
    return {
        doctype
        for doctype, dotted in mapping.items()
        if dotted.startswith("apex.salis.permissions.")
    }


def _shipped_doctypes():
    """DocType name -> shipped JSON."""
    out = {}
    for path in sorted(glob.glob(_DOCTYPE_GLOB)):
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict) and data.get("doctype") == "DocType" and data.get("name"):
            out[data["name"]] = data
    return out


def readers_of(doctypes, names):
    """role -> {doctype: if_owner flag} over the permlevel-0 read DocPerms on `names`.

    Only permlevel 0 matters: a permlevel>0 row governs FIELD visibility, never which rows
    the query returns.
    """
    out = {}
    for name in sorted(names):
        data = doctypes.get(name)
        if not data:
            continue
        for row in data.get("permissions") or []:
            role = row.get("role")
            if not role or not row.get("read") or row.get("permlevel"):
                continue
            out.setdefault(role, {})[name] = bool(row.get("if_owner"))
    return out


def zeroed_roles(readers, unscoped):
    """Roles whose granted lists can only ever return ``1=0``.

    Pure over its inputs so the self-test below can drive it with a planted role.
    """
    declared = unscoped | PROJECT_SCOPED_ROLES | OWNER_SCOPED_ROLES | _SUPERUSERS
    return {role for role in readers if role not in declared}


class TestSalisScopeRolePartition(unittest.TestCase):
    """Every reader of a project-scoped Salis DocType sits in a declared bucket."""

    def setUp(self):
        self.unscoped = unscoped_roles()
        self.scoped = scoped_doctypes()
        self.doctypes = _shipped_doctypes()
        self.readers = readers_of(self.doctypes, self.scoped)

    def test_scan_finds_the_wiring(self):
        self.assertIn("Salis Vehicle", self.scoped)
        self.assertIn("Driver Clearance", self.scoped)
        self.assertTrue(self.readers, "no DocPerm readers found — the scan broke")

    def test_unscoped_roles_parsed_from_source(self):
        self.assertIn("Fleet Manager", self.unscoped)
        self.assertIn("Internal Auditor", self.unscoped)

    def test_no_role_is_granted_a_list_it_can_never_see(self):
        found = zeroed_roles(self.readers, self.unscoped)
        self.assertEqual(
            found,
            set(KNOWN_ZEROED_ROLES),
            "role(s) hold a read DocPerm on a project-scoped Salis DocType while sitting in "
            "no declared bucket. permission_query_conditions will return '1=0' for them "
            "(apex_core/utils/permission_scope.scope_condition), so every list they were "
            "granted renders zero rows. Add the role to UNSCOPED_ROLES, to "
            "PROJECT_SCOPED_ROLES if it is issued Project User Permissions, or to "
            "OWNER_SCOPED_ROLES with an if_owner DocPerm. Affected doctypes: "
            f"{ {role: sorted(self.readers[role]) for role in found} }",
        )

    def test_the_detector_flags_a_planted_role(self):
        """Proof the guard can fail: a role reading a scoped DocType but in no bucket."""
        readers = dict(self.readers)
        readers["_A171 Planted Role"] = {"Salis Vehicle": False}
        self.assertIn(
            "_A171 Planted Role",
            zeroed_roles(readers, self.unscoped),
            "the detector missed an unclassified reader — the guard proves nothing",
        )

    def test_the_detector_flags_the_regression_it_was_written_for(self):
        """With the persona removed from UNSCOPED_ROLES, A-171 must reappear."""
        self.assertIn(
            GRO_ROLE,
            zeroed_roles(self.readers, self.unscoped - {GRO_ROLE}),
            "removing the persona from UNSCOPED_ROLES no longer reproduces A-171",
        )

    def test_the_buckets_are_disjoint(self):
        """A role cannot be both unscoped and project-scoped; that contradiction would let
        the partition pass while the runtime behaviour is undefined."""
        for other in (PROJECT_SCOPED_ROLES, OWNER_SCOPED_ROLES):
            with self.subTest(bucket=sorted(other)):
                self.assertEqual(self.unscoped & other, set())
        self.assertEqual(PROJECT_SCOPED_ROLES & OWNER_SCOPED_ROLES, set())

    def test_owner_scoped_roles_actually_hold_if_owner(self):
        """The owner bucket is only honest if every one of its rows carries if_owner —
        otherwise the OR clause the query adds never matches and the role is zeroed too."""
        for role in OWNER_SCOPED_ROLES:
            rows = self.readers.get(role, {})
            self.assertTrue(rows, f"{role} is declared owner-scoped but reads nothing")
            plain = sorted(dt for dt, is_owner in rows.items() if not is_owner)
            self.assertEqual(
                plain,
                [],
                f"{role} holds a non-if_owner read DocPerm on {plain}; it is issued no "
                "Project User Permission, so those lists resolve to '1=0'",
            )

    def test_baseline_entries_carry_a_written_reason(self):
        for role, reason in KNOWN_ZEROED_ROLES.items():
            with self.subTest(role=role):
                self.assertTrue(reason and reason.strip(), f"'{role}' has no reason")


class TestGovernmentRelationsOfficerScope(unittest.TestCase):
    """A-171's own outcome, asserted by name so it cannot be ratcheted away."""

    def setUp(self):
        self.unscoped = unscoped_roles()

    def test_the_persona_is_unscoped(self):
        self.assertIn(
            GRO_ROLE,
            self.unscoped,
            f"{GRO_ROLE} left UNSCOPED_ROLES; its granted Salis lists go back to zero rows",
        )

    def test_the_persona_is_never_frozen_into_the_baseline(self):
        self.assertNotIn(
            GRO_ROLE,
            KNOWN_ZEROED_ROLES,
            "A-171 must stay fixed in permissions.py, never frozen as a known gap",
        )

    def test_the_persona_holds_no_field_level_grant(self):
        """Being unscoped removes a ROW filter only. permlevel>0 fields (national id,
        licence number, phone, driver id) stay closed because the persona holds no
        permlevel>0 DocPerm anywhere."""
        elevated = []
        for name, data in _shipped_doctypes().items():
            for row in data.get("permissions") or []:
                if row.get("role") == GRO_ROLE and row.get("permlevel"):
                    elevated.append((name, row.get("permlevel")))
        self.assertEqual(
            elevated,
            [],
            f"{GRO_ROLE} gained a permlevel>0 DocPerm on {elevated}; unscoping it would now "
            "also widen FIELD visibility, which A-171 did not authorise",
        )


if __name__ == "__main__":
    unittest.main()
