# Copyright (c) 2026, afmcoltd
"""The Gender restriction removes the surplus and refuses to strand a row that points at one."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.setup import KEPT_GENDERS, restrict_genders


class TestRestrictGendersToTwo(FrappeTestCase):
    def test_surplus_gender_is_removed(self):
        if not frappe.db.exists("Gender", "Genderqueer"):
            frappe.get_doc({"doctype": "Gender", "gender": "Genderqueer"}).insert(
                ignore_permissions=True
            )

        result = restrict_genders()

        self.assertIn("Genderqueer", result["removed"])
        self.assertFalse(frappe.db.exists("Gender", "Genderqueer"))
        for kept in KEPT_GENDERS:
            self.assertTrue(frappe.db.exists("Gender", kept), f"{kept} must survive")

    def test_gender_in_use_survives(self):
        if not frappe.db.exists("Gender", "Other"):
            frappe.get_doc({"doctype": "Gender", "gender": "Other"}).insert(
                ignore_permissions=True
            )
        employee = frappe.get_all("Employee", limit=1, pluck="name")
        if not employee:
            self.skipTest("no Employee on this site to hold the reference")
        previous = frappe.db.get_value("Employee", employee[0], "gender")
        frappe.db.set_value("Employee", employee[0], "gender", "Other")

        try:
            result = restrict_genders()
            self.assertIn("Other", result["in_use"])
            self.assertTrue(frappe.db.exists("Gender", "Other"))
        finally:
            frappe.db.set_value("Employee", employee[0], "gender", previous)
