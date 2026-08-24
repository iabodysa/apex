# Copyright (c) 2026, afmcoltd


import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup.app_owned_permissions_seed import (
    _ALL_PTYPES,
    APP_OWNED_PERMISSIONS,
)


class TestAppOwnedPermissionsGrantOnlyWhatTheyName(FrappeTestCase):

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
