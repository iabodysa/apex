# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.doctype.housing_checkout.housing_checkout import create_departure_transport
from apex.tests.factories import make_assignment, make_building, make_employee, make_project


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


def _grant_building(email, building):
    if not frappe.db.exists(
        "User Permission", {"user": email, "allow": "Building", "for_value": building}
    ):
        frappe.get_doc({
            "doctype": "User Permission",
            "user": email,
            "allow": "Building",
            "for_value": building,
        }).insert(ignore_permissions=True)
    return email


def _building():
    return make_building("TR Permission Building")


def _submitted_checkout(suffix):
    building = _building()
    project = make_project("TR Permission Project")
    employee = make_employee(f"TR Permission Worker {suffix}", company=building.company)
    assignment = make_assignment(
        employee.name,
        building.name,
        project,
        room_number=f"TRPERM-{suffix}-R",
        bed_code=f"TRPERM-{suffix}-B",
    )
    checkout = frappe.get_doc({
        "doctype": "Housing Checkout",
        "assignment": assignment,
        "checkout_date": today(),
        "checkout_reason": "Final Exit",
    })
    checkout.insert(ignore_permissions=True)
    checkout.submit()
    return checkout.name


class TestAHousingRoleRaisesATransportRequestUnderItsOwnPermission(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_an_accommodation_manager_may_raise_one(self):
        checkout = _submitted_checkout("am")
        frappe.set_user(_user("_t_accom_mgr@apex.test", "Accommodation Manager"))
        request = create_departure_transport(checkout)
        self.assertTrue(frappe.db.exists("Transport Request", request))

    def test_a_resident_supervisor_may_raise_one(self):
        checkout = _submitted_checkout("rs")
        supervisor = _user("_t_res_sup@apex.test", "Resident Supervisor")
        _grant_building(supervisor, _building().name)
        frappe.set_user(supervisor)
        request = create_departure_transport(checkout)
        self.assertTrue(frappe.db.exists("Transport Request", request))

    def test_the_checkout_carries_the_request_it_raised(self):
        checkout = _submitted_checkout("link")
        frappe.set_user(_user("_t_accom_mgr@apex.test", "Accommodation Manager"))
        request = create_departure_transport(checkout)
        self.assertEqual(
            frappe.db.get_value("Housing Checkout", checkout, "departure_transport_request"),
            request,
        )

    def test_a_second_call_returns_the_same_request(self):
        checkout = _submitted_checkout("once")
        frappe.set_user(_user("_t_accom_mgr@apex.test", "Accommodation Manager"))
        first = create_departure_transport(checkout)
        self.assertEqual(create_departure_transport(checkout), first)

    def test_a_role_without_the_grant_is_refused(self):
        checkout = _submitted_checkout("none")
        frappe.set_user(_user("_t_no_grant@apex.test", "Internal Auditor"))
        with self.assertRaises(frappe.PermissionError):
            create_departure_transport(checkout)
