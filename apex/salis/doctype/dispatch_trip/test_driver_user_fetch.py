# Copyright (c) 2026, AFMCO and contributors
"""Driver-user mirror fetch.

Dispatch Trip and Fuel Request each carry a local read-only ``driver_user`` that
fetches ``driver.driver_user`` so a native Notification can target the driver's
portal user (``receiver_by_document_field`` reads a LOCAL field — it does not
follow a dotted cross-doc path). These tests prove the fetch lands the driver's
user on each transaction document.

``test_ignore`` prunes the auto-dependency walk: Salis Driver links to Employee
(pulling the ERPNext HR masters) and the transaction docs link to Salis Vehicle.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

test_ignore = [
    "Employee",
    "Company",
    "Project",
    "Salis Vehicle",
    "Salis Driver",
    "User",
    "Role",
]


def _driver_user_email():
    email = "tdu_driver@example.com"
    if not frappe.db.exists("User", email):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "TDU Driver",
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True)
    return email


def _driver_with_user(full_name, user):
    name = frappe.db.get_value("Salis Driver", {"full_name": full_name}, "name")
    if not name:
        name = (
            frappe.get_doc(
                {
                    "doctype": "Salis Driver",
                    "full_name": full_name,
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
    # [#iuqgwy]
    frappe.db.set_value("Salis Driver", name, "driver_user", user)
    return name


def _vehicle(plate, driver):
    name = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
    if not name:
        name = (
            frappe.get_doc(
                {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
            )
            .insert(ignore_permissions=True)
            .name
        )
    return name


class TestDriverUserFetch(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.user = _driver_user_email()
        self.driver = _driver_with_user("TDU Mirror Driver", self.user)

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_dispatch_trip_mirrors_driver_user(self):
        trip = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "trip_date": today(),
                "driver": self.driver,
                "status": "Planned",
            }
        )
        trip.insert(ignore_permissions=True)
        self.assertEqual(
            trip.driver_user,
            self.user,
            "Dispatch Trip.driver_user must fetch the linked driver's portal user.",
        )
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Dispatch Trip", trip.name, force=True, ignore_permissions=True
            )
        )

    def test_fuel_request_mirrors_driver_user(self):
        vehicle = _vehicle("TDU-FR-1", self.driver)
        fr = frappe.get_doc(
            {
                "doctype": "Fuel Request",
                "request_type": "Standard",
                "vehicle": vehicle,
                "driver": self.driver,
                "request_date": today(),
                "requested_litres": 40,
                "status": "Pending",
            }
        )
        fr.insert(ignore_permissions=True)
        self.assertEqual(
            fr.driver_user,
            self.user,
            "Fuel Request.driver_user must fetch the linked driver's portal user.",
        )
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Fuel Request", fr.name, force=True, ignore_permissions=True
            )
        )
