# Copyright (c) 2026, AFMCO and contributors
"""The core-master grant must stay a PICKER grant, now declared metadata instead of a
Python seeder: apex/habitat/custom/employee.json, project.json and cost_center.json
carry the rows, imported by frappe's own ``sync_customizations`` on every migrate
(frappe/migrate.py:145) — no hooks.py wiring, no seeder module.

Custom DocPerm defaults ``read`` and ``export`` to 1 (``custom_docperm.json:81,170``),
so a row asked for with ptype="select" is born granting more than a Link picker needs
unless the export explicitly clears them — which is what these tests grade, against
the exported JSON directly and against the live DocPerm rows a migrate produces from it.

Run standalone:
  bench --site <site> run-tests --module apex.apex_core.setup.seeders.test_habitat_core_link_perms_seed
"""

import json
import os
import unittest

import frappe
from frappe import get_module_path, scrub
from frappe.permissions import get_role_permissions
from frappe.tests.utils import FrappeTestCase

CORE_LINK_MASTERS = ("Employee", "Project", "Cost Center")

HABITAT_LINK_ROLES = ("Accommodation Manager", "Resident Supervisor", "Internal Auditor")

SALIS_LINK_MASTERS = ("Project",)

SALIS_LINK_ROLES = (
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
    "Finance Manager",
)

# Everything a picker does NOT need. `read` is the important one: it is the difference
# between naming an Employee in a Link field and opening that Employee's record.
FORBIDDEN = ("read", "write", "create", "delete", "report", "import", "share")


def _custom_perms(doctype):
    path = os.path.join(get_module_path("Habitat"), "custom", scrub(doctype) + ".json")
    with open(path) as f:
        return json.load(f)["custom_perms"]


def _exported_row(doctype, role):
    rows = [
        p
        for p in _custom_perms(doctype)
        if p.get("role") == role and not p.get("permlevel") and not p.get("if_owner")
    ]
    return rows[0] if rows else None


def _db_rows(doctype, role):
    return frappe.get_all(
        "Custom DocPerm",
        filters={"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
        fields=["name", "select", *FORBIDDEN, "export"],
    )


class TestHabitatCoreLinkPermsExport(unittest.TestCase):
    """Reads the exported JSON directly -- no site needed."""

    def test_the_habitat_and_salis_roles_are_declared_select_only(self):
        pairs = [(dt, role) for dt in CORE_LINK_MASTERS for role in HABITAT_LINK_ROLES]
        pairs += [(dt, role) for dt in SALIS_LINK_MASTERS for role in SALIS_LINK_ROLES]
        for doctype, role in pairs:
            with self.subTest(doctype=doctype, role=role):
                row = _exported_row(doctype, role)
                self.assertIsNotNone(row, f"no exported row for {doctype}/{role}")
                self.assertTrue(row.get("select"))
                widened = [p for p in (*FORBIDDEN, "export") if row.get(p)]
                self.assertEqual(
                    widened, [], f"{doctype}/{role} widened past select: {widened}"
                )

    def test_sync_on_migrate_is_set(self):
        for doctype in CORE_LINK_MASTERS:
            path = os.path.join(
                get_module_path("Habitat"), "custom", scrub(doctype) + ".json"
            )
            with open(path) as f:
                self.assertTrue(
                    json.load(f).get("sync_on_migrate"),
                    f"{doctype}.json must sync on every migrate, matching the seeder "
                    "it replaced (wired into both after_install and after_migrate)",
                )

    def test_the_platform_role_is_left_to_the_site_administrator(self):
        """System Manager writes the same Project-anchored documents and is deliberately
        not granted here — re-granting a core master to a platform role is a site
        decision, the same line the Habitat set already draws."""
        for doctype in SALIS_LINK_MASTERS:
            self.assertIsNone(_exported_row(doctype, "System Manager"))


class TestHabitatCoreLinkPermsLive(FrappeTestCase):
    """The exported rows only matter if a migrate actually produced them on the site
    and the permission layer honours them -- graded against the live DB, not re-run
    through a seeder that no longer exists."""

    def test_the_declared_rows_exist_on_the_site(self):
        pairs = [(dt, role) for dt in CORE_LINK_MASTERS for role in HABITAT_LINK_ROLES]
        pairs += [(dt, role) for dt in SALIS_LINK_MASTERS for role in SALIS_LINK_ROLES]
        for doctype, role in pairs:
            with self.subTest(doctype=doctype, role=role):
                rows = _db_rows(doctype, role)
                self.assertEqual(len(rows), 1, "expected exactly one level-0 rule")
                self.assertTrue(rows[0]["select"])
                widened = [p for p in (*FORBIDDEN, "export") if rows[0][p]]
                self.assertEqual(widened, [], f"{doctype}/{role} widened past select")

    def test_select_is_what_the_permission_layer_reports(self):
        """The rule is only worth anything if ``get_role_permissions`` agrees — that is
        the function both the Link validator and the report match-conditions consult."""
        for doctype in CORE_LINK_MASTERS:
            with self.subTest(doctype=doctype):
                perms = get_role_permissions(
                    frappe.get_meta(doctype), user="Administrator"
                )
                self.assertTrue(perms.get("select") or perms.get("read"))


if __name__ == "__main__":
    unittest.main()
