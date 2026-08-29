# Copyright (c) 2026, afmcoltd


import frappe
from frappe.tests.utils import FrappeTestCase

from apex.setup import (
    ACCOMMODATION_ITEM_GROUPS,
    KEPT_GENDERS,
    create_accommodation_item_defaults,
    restrict_genders,
)

_UNGRANTED_USER = "install.identity.probe@apex.example"
_PROBE_GROUP = "Apex Install Identity Probe Group"
_PROBE_GENDER = "Apex Install Identity Probe Gender"
_PROBE_ITEM = "APEX-INSTALL-IDENTITY-PROBE"


class TestInstallSeedersRunOnTheInstallerIdentity(FrappeTestCase):

    def setUp(self):
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")

    def _ungranted_user(self):
        if not frappe.db.exists("User", _UNGRANTED_USER):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": _UNGRANTED_USER,
                    "first_name": "Install Identity Probe",
                    "send_welcome_email": 0,
                    "roles": [{"role": "Employee Self Service"}],
                }
            ).insert()
        return _UNGRANTED_USER

    def _item_group_root(self):
        roots = frappe.get_all(
            "Item Group", filters={"parent_item_group": ["is", "not set"]}, pluck="name"
        )
        self.assertTrue(roots, "no Item Group root on this site")
        return roots[0]

    def _probe_group_payload(self):
        return {
            "doctype": "Item Group",
            "item_group_name": _PROBE_GROUP,
            "parent_item_group": self._item_group_root(),
            "is_group": 0,
        }

    def _probe_item_payload(self):
        return {
            "doctype": "Item",
            "item_code": _PROBE_ITEM,
            "item_name": _PROBE_ITEM,
            "item_group": ACCOMMODATION_ITEM_GROUPS[0],
            "stock_uom": frappe.db.get_value("UOM", {"name": "Nos"}, "name") or "Nos",
            "is_stock_item": 0,
        }

    def test_the_installer_seeds_accommodation_defaults(self):
        self.assertTrue(create_accommodation_item_defaults())
        for group in ACCOMMODATION_ITEM_GROUPS:
            self.assertTrue(frappe.db.exists("Item Group", group), f"{group} is not seeded")

    def test_the_installer_may_insert_an_item_group(self):
        doc = frappe.get_doc(self._probe_group_payload()).insert()
        self.assertTrue(frappe.db.exists("Item Group", doc.name))

    def test_a_user_without_the_item_group_grant_may_not_insert_one(self):
        payload = self._probe_group_payload()
        frappe.set_user(self._ungranted_user())
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc(payload).insert()

    def test_the_installer_may_insert_an_item(self):
        doc = frappe.get_doc(self._probe_item_payload()).insert()
        self.assertTrue(frappe.db.exists("Item", doc.name))

    def test_a_user_without_the_item_grant_may_not_insert_one(self):
        payload = self._probe_item_payload()
        frappe.set_user(self._ungranted_user())
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc(payload).insert()

    def test_the_installer_removes_a_surplus_gender_and_keeps_the_two(self):
        if not frappe.db.exists("Gender", _PROBE_GENDER):
            frappe.get_doc({"doctype": "Gender", "gender": _PROBE_GENDER}).insert()
        removed = restrict_genders()["removed"]
        self.assertIn(_PROBE_GENDER, removed)
        for kept in KEPT_GENDERS:
            self.assertTrue(frappe.db.exists("Gender", kept), f"{kept} was removed")

    def test_a_user_without_the_gender_grant_may_not_delete_one(self):
        if not frappe.db.exists("Gender", _PROBE_GENDER):
            frappe.get_doc({"doctype": "Gender", "gender": _PROBE_GENDER}).insert()
        frappe.set_user(self._ungranted_user())
        with self.assertRaises(frappe.PermissionError):
            frappe.delete_doc("Gender", _PROBE_GENDER)
