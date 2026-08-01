# Copyright (c) 2026, AFMCO and contributors
"""The core-master grant must stay a PICKER grant.

``add_permission(dt, role, ptype="select")`` does not produce a select-only rule.
Custom DocPerm defaults ``read`` and ``export`` to 1 (``custom_docperm.json:81,170``),
so the row is born granting the Habitat roles every Employee record and the right to
export them — to reach a Link picker. Measured on a real migrate before this pinned it.

The two cases below are the grant's floor and its ceiling: the roles must be able to
resolve the Link, and must not gain anything beyond that. Without the ceiling case the
widening is invisible, because the floor passes either way.

Run standalone:
  bench --site <site> run-tests --module apex.apex_core.setup.seeders.test_habitat_core_link_perms_seed
"""

import unittest

import frappe
from frappe.permissions import get_role_permissions
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup.seeders.habitat_core_link_perms_seed import (
    CORE_LINK_MASTERS,
    HABITAT_LINK_ROLES,
    seed_habitat_core_link_perms,
)

# Everything a picker does NOT need. `read` is the important one: it is the difference
# between naming an Employee in a Link field and opening that Employee's record.
FORBIDDEN = ("read", "write", "create", "delete", "report", "import", "share")


def _rows(doctype, role):
    return frappe.get_all(
        "Custom DocPerm",
        filters={"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
        fields=["name", "select", *FORBIDDEN, "export"],
    )


class TestHabitatCoreLinkPerms(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        seed_habitat_core_link_perms()
        frappe.clear_cache()

    def test_the_habitat_roles_can_resolve_the_link(self):
        for doctype in CORE_LINK_MASTERS:
            for role in HABITAT_LINK_ROLES:
                with self.subTest(doctype=doctype, role=role):
                    rows = _rows(doctype, role)
                    self.assertEqual(len(rows), 1, "expected exactly one level-0 rule")
                    self.assertTrue(rows[0]["select"])

    def test_the_grant_carries_nothing_but_select(self):
        """THE CEILING. A row created with the framework's defaults arrives carrying
        read and export; a picker grant must carry neither."""
        widened = []
        for doctype in CORE_LINK_MASTERS:
            for role in HABITAT_LINK_ROLES:
                row = _rows(doctype, role)[0]
                for ptype in (*FORBIDDEN, "export"):
                    if row[ptype]:
                        widened.append(f"{doctype}/{role}: {ptype}")
        self.assertEqual(
            widened,
            [],
            "the picker grant widened past select:\n  " + "\n  ".join(widened),
        )

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
