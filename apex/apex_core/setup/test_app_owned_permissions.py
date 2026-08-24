# Copyright (c) 2026, afmcoltd

"""Every seeded grant gives exactly the permission types it names, and no other.

``frappe.permissions.add_permission`` grants ``read`` by default, so a row seeded with
its default would hand a role the ability to open records it is only meant to raise.
Thirteen of these rows grant ``select`` alone — the Link-field picker — and two grant
``create`` alone, which is what lets a telecom coordinator raise a draft Material
Request or Payment Entry without gaining the procurement and payment surface those
DocTypes otherwise carry.

The test reads Custom DocPerm rather than calling ``has_permission``, because the row is
the shipped artefact: a User Permission or a role a site adds later changes the answer
``has_permission`` gives without changing what this app granted.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup.app_owned_permissions_seed import (
    _ALL_PTYPES,
    APP_OWNED_PERMISSIONS,
)


class TestAppOwnedPermissionsGrantOnlyWhatTheyName(FrappeTestCase):
    """Each seeded row carries its declared permission types and zero others."""

    def test_every_seeded_row_matches_its_declaration(self):
        checked = 0
        for doctype, role, permlevel, granted in APP_OWNED_PERMISSIONS:
            if not frappe.db.exists("DocType", doctype) or not frappe.db.exists("Role", role):
                continue
            row = frappe.db.get_value(
                "Custom DocPerm",
                {"parent": doctype, "role": role, "permlevel": permlevel},
                _ALL_PTYPES,
                as_dict=True,
            )
            self.assertIsNotNone(row, f"no Custom DocPerm row for {role} on {doctype}")
            checked += 1
            for ptype in _ALL_PTYPES:
                expected = 1 if ptype in granted else 0
                self.assertEqual(
                    int(row[ptype] or 0),
                    expected,
                    f"{role} on {doctype}: {ptype} is {row[ptype]}, declared {expected}",
                )
        self.assertGreater(checked, 0, "no seeded row was present to check")

    def test_the_telecom_coordinator_may_raise_a_draft_but_not_read_one(self):
        for doctype in ("Material Request", "Payment Entry"):
            row = frappe.db.get_value(
                "Custom DocPerm",
                {"parent": doctype, "role": "SIM Operations User", "permlevel": 0},
                ["create", "read", "write", "submit", "delete"],
                as_dict=True,
            )
            self.assertIsNotNone(row, f"SIM Operations User holds no row on {doctype}")
            self.assertEqual(int(row.create or 0), 1, f"cannot raise a draft {doctype}")
            for ptype in ("read", "write", "submit", "delete"):
                self.assertEqual(
                    int(row[ptype] or 0), 0, f"{ptype} on {doctype} widens past raising a draft"
                )
