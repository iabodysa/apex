# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _user(email, role):
    if not frappe.db.exists("User", email):
        doc = frappe.new_doc("User")
        doc.email = email
        doc.first_name = email.split("@")[0]
        doc.send_welcome_email = 0
        doc.insert(ignore_permissions=True)
    doc = frappe.get_doc("User", email)
    doc.set("roles", [])
    doc.append("roles", {"role": role})
    doc.save(ignore_permissions=True)
    return email


def _request(employee):
    return frappe.get_doc({
        "doctype": "Transport Request",
        "service_line": "Inter-City Relocation",
        "request_type": "Inter-City Relocation",
        "source_channel": "Desk",
        "status": "New",
        "workers": [{"employee": employee}],
    })


class TestAHousingRoleRaisesATransportRequestUnderItsOwnPermission(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")

    def setUp(self):
        if not self.employee:
            self.skipTest("the site carries no active Employee to put on the manifest")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_an_accommodation_manager_may_insert_one(self):
        frappe.set_user(_user("_t_accom_mgr@apex.test", "Accommodation Manager"))
        doc = _request(self.employee)
        doc.insert()
        self.assertTrue(frappe.db.exists("Transport Request", doc.name))

    def test_a_resident_supervisor_may_insert_one(self):
        frappe.set_user(_user("_t_res_sup@apex.test", "Resident Supervisor"))
        doc = _request(self.employee)
        doc.insert()
        self.assertTrue(frappe.db.exists("Transport Request", doc.name))

    def test_a_role_without_the_grant_is_refused(self):
        frappe.set_user(_user("_t_no_grant@apex.test", "Internal Auditor"))
        with self.assertRaises(frappe.PermissionError):
            _request(self.employee).insert()
