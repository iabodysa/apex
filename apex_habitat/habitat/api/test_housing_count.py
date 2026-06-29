# Copyright (c) 2026, AFMCO and contributors
"""housing_count enforces the Housing Inventory building scope + write DocPerm.

The housing count portal's backend reuses the Housing Inventory DocType and its
existing count fields. These tests pin the contract the portal relies on:

- A Resident Supervisor scoped (User Permission) to building b1 sees ONLY b1's
  items via get_inventory_for_building (the building scope applies — no
  ignore_permissions), never b2's.
- That scoped supervisor cannot write a b2 item via submit_counts (the per-doc
  building scope rejects the cross-building line; nothing is saved).
- An in-scope submit sets counted_quantity and the controller DERIVES
  quantity_variance (never client-set) and stamps last_count_date.
- A read-only role (Internal Auditor: read but no write on Housing Inventory) is
  rejected by submit_counts' write gate.

The Resident Supervisor write grant is the recommended decision recorded for
T-684 (a building-scoped write so field-counting works). The test ensures that
grant is present (adding a Custom DocPerm if the JSON has not yet migrated) so it
is self-contained on any test bench.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.habitat.api.housing_count import (
    get_inventory_for_building,
    submit_counts,
)


def _h(n=6):
    return frappe.generate_hash(length=n).upper()


class TestHousingCount(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._ensure_supervisor_write()
        # Two estates; a Resident Supervisor scoped (User Permission) to ONLY b1.
        cls.b1 = cls._building()
        cls.b2 = cls._building()
        cls.scoped = cls._scoped_supervisor(cls.b1)
        cls.auditor = cls._auditor()
        # One inventory line per building.
        cls.item1 = cls._item(cls.b1, expected=10)
        cls.item2 = cls._item(cls.b2, expected=5)

    @classmethod
    def _ensure_supervisor_write(cls):
        # The recommended decision: Resident Supervisor gets a building-scoped write
        # on Housing Inventory. Guarantee it for the test even if the JSON DocPerm
        # has not migrated into this bench yet, via a temporary Custom DocPerm.
        has_write = frappe.db.exists(
            "Custom DocPerm",
            {"parent": "Housing Inventory", "role": "Resident Supervisor", "permlevel": 0, "write": 1},
        ) or any(
            p.role == "Resident Supervisor" and p.write
            for p in frappe.get_meta("Housing Inventory").permissions
        )
        if has_write:
            return
        perm = frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": "Housing Inventory",
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": "Resident Supervisor",
                "permlevel": 0,
                "read": 1,
                "write": 1,
            }
        )
        perm.insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Custom DocPerm", perm.name, force=True, ignore_permissions=True
        )
        frappe.clear_cache(doctype="Housing Inventory")

    @classmethod
    def _building(cls):
        doc = frappe.get_doc(
            {"doctype": "Accommodation Building", "building_name": "HC-" + _h()}
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Accommodation Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _item(cls, building, expected=0):
        doc = frappe.get_doc(
            {
                "doctype": "Housing Inventory",
                "naming_series": "HINV-.YYYY.-.#####",
                "item_name": "Item " + _h(),
                "item_category": "Furniture",
                "building": building,
                "expected_quantity": expected,
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Housing Inventory", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _user(cls, role):
        email = "hc-{0}@example.com".format(_h()).lower()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "HC",
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc, "User", email, force=True, ignore_permissions=True
        )
        return email

    @classmethod
    def _scoped_supervisor(cls, building):
        email = cls._user("Resident Supervisor")
        up = frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": email,
                "allow": "Accommodation Building",
                "for_value": building,
            }
        )
        up.insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc, "User Permission", up.name, force=True, ignore_permissions=True
        )
        return email

    @classmethod
    def _auditor(cls):
        return cls._user("Internal Auditor")

    def setUp(self):
        self.addCleanup(frappe.set_user, "Administrator")

    # Read scope: building permission confines what a supervisor can see.
    def test_scoped_supervisor_sees_only_their_building(self):
        frappe.set_user(self.scoped)
        out = get_inventory_for_building(self.b1)
        names = {it["name"] for it in out["items"]}
        self.assertIn(self.item1, names)
        self.assertNotIn(self.item2, names)

    def test_scoped_supervisor_off_building_sees_nothing(self):
        frappe.set_user(self.scoped)
        out = get_inventory_for_building(self.b2)
        self.assertEqual(out["items"], [])

    def test_inventory_payload_carries_condition_options(self):
        frappe.set_user(self.scoped)
        out = get_inventory_for_building(self.b1)
        self.assertIn("Good", out["conditions"])
        self.assertIn("Damaged", out["conditions"])

    # Write scope: submit_counts records the count and the controller derives variance.
    def test_in_scope_submit_sets_count_and_derives_variance(self):
        frappe.set_user(self.scoped)
        out = submit_counts(
            self.b1,
            [{"name": self.item1, "counted_quantity": 7, "condition": "Fair"}],
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["saved"], 1)
        frappe.set_user("Administrator")
        row = frappe.get_doc("Housing Inventory", self.item1)
        self.assertEqual(row.counted_quantity, 7)
        # expected 10 - counted 7 -> variance derived by the controller, not the API.
        self.assertEqual(row.quantity_variance, -3)
        self.assertIsNotNone(row.last_count_date)
        self.assertEqual(row.condition, "Fair")

    def test_cross_building_write_blocked(self):
        # A b1-scoped supervisor must not write a b2 item. submit_counts records the
        # failure per row (savepoint-isolated) and saves nothing for b2.
        frappe.set_user(self.scoped)
        out = submit_counts(self.b2, [{"name": self.item2, "counted_quantity": 99}])
        self.assertFalse(out["ok"])
        self.assertEqual(out["saved"], 0)
        self.assertEqual(out["failed"], 1)
        frappe.set_user("Administrator")
        # b2's item is untouched (still its default zero count).
        self.assertEqual(
            frappe.db.get_value("Housing Inventory", self.item2, "counted_quantity"), 0
        )

    def test_read_only_role_rejected_by_write_gate(self):
        # Internal Auditor has read but NO write on Housing Inventory: the up-front
        # has_permission(..., "write", throw=True) gate must reject the call.
        frappe.set_user(self.auditor)
        with self.assertRaises(frappe.PermissionError):
            submit_counts(self.b1, [{"name": self.item1, "counted_quantity": 1}])

    def test_malformed_json_lines_raises_validation_error(self):
        # A malformed `lines` JSON body must surface as a clean ValidationError, not
        # a raw JSONDecodeError 500. The scoped supervisor clears the write gate +
        # building check, so the call reaches the json.loads guard.
        frappe.set_user(self.scoped)
        with self.assertRaises(frappe.ValidationError):
            submit_counts(self.b1, "{not valid json")
