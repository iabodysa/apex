# Copyright (c) 2026, AFMCO and contributors
"""Driver-user mirror fetch.

Dispatch Trip and Fuel Request each carry a local read-only ``driver_user`` that
fetches ``driver.driver_user`` so a native Notification can target the driver's
portal user (``receiver_by_document_field`` reads a LOCAL field — it does not
follow a dotted cross-doc path). These tests prove the fetch lands the driver's
user on each transaction document.

The rider, the vehicle and the portal user are all shipped fixtures — naming them as
dependencies is what replaced the ``test_ignore`` block that used to prune the walk behind
their construction. The user is the one ERPNext's own Employee fixture is wired to, so the
mirror has a real portal account to land without this file minting one. The link written
onto the borrowed rider is cleared again after each case.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

test_dependencies = ["Salis Driver", "Salis Vehicle", "Employee"]

DRIVER_NAME = "_Test Driver"
PLATE = "_T ABC 1001"
# The portal account ERPNext's _Test Employee fixture carries in user_id.
PORTAL_USER = "test@example.com"


class TestDriverUserFetch(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.user = PORTAL_USER
        self.driver = frappe.db.get_value("Salis Driver", {"full_name": DRIVER_NAME}, "name")
        self.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": PLATE}, "name")
        self.addCleanup(frappe.db.set_value, "Salis Driver", self.driver, "driver_user", None)
        frappe.db.set_value("Salis Driver", self.driver, "driver_user", self.user)

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
        fr = frappe.get_doc(
            {
                "doctype": "Fuel Request",
                "request_type": "Standard",
                "vehicle": self.vehicle,
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
