"""Driver-facing Salis notification wiring (T-562).

Proves that the two driver-relevant notifications resolve to the affected
driver's own User and drop a Notification Log row for that driver:

* Blocked Driver Clearance  -> the driver whose clearance is blocked
* Vehicle Compliance Expiring Soon -> the current driver of the vehicle

The driver's User is reached through a denormalised single-hop fetch chain
(Salis Driver.driver_user <- employee.user_id; the source docs mirror it),
because Notification recipients read a flat local field and validate it as an
email, and ``receiver_by_document_field`` cannot walk a dotted cross-doc path.

The in-app delivery (Notification Log) is exercised through
``create_system_notification`` — the System Notification channel both alerts
ship — so the assertion does not depend on a configured outgoing mail server.
"""

from __future__ import annotations

import frappe
from frappe.email.doctype.notification.notification import get_context
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase

test_ignore = ["Company", "Employee", "User"]


class TestDriverClearanceNotification(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = frappe.generate_hash(length=6).lower()

        self.user = frappe.get_doc(
            {
                "doctype": "User",
                "email": f"driver-{tag}@example.com",
                "first_name": f"Driver {tag}",
                "enabled": 1,
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True).name

        company = frappe.db.get_value("Company", {}) or frappe.get_doc(
            {"doctype": "Company", "company_name": "Test Co", "default_currency": "SAR"}
        ).insert(ignore_permissions=True).name

        self.employee = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": f"Driver {tag}",
                "company": company,
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
                "user_id": self.user,
            }
        ).insert(ignore_permissions=True).name

        self.driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": f"Driver {tag}",
                "status": "Active",
                "employee": self.employee,
            }
        ).insert(ignore_permissions=True).name

    def _fire(self, notification, doc):
        frappe.get_doc("Notification", notification).create_system_notification(
            doc, get_context(doc)
        )

    def _driver_logs(self, doctype, name):
        return frappe.get_all(
            "Notification Log",
            filters={
                "for_user": self.user,
                "document_type": doctype,
                "document_name": name,
            },
        )

    def test_driver_user_is_mirrored_onto_salis_driver(self):
        # The single-hop fetch chain must land the driver's login User locally,
        # otherwise the flat recipient field can never resolve to an email.
        self.assertEqual(
            frappe.db.get_value("Salis Driver", self.driver, "driver_user"), self.user
        )

    def test_blocked_clearance_notifies_the_driver(self):
        clearance = frappe.get_doc(
            {
                "doctype": "Driver Clearance",
                "driver": self.driver,
                "clearance_reason": "Termination",
            }
        ).insert(ignore_permissions=True)
        # Status is governed by the Driver Clearance Workflow; reach Blocked
        # through the native transition rather than writing the field directly.
        clearance = apply_workflow(clearance, "Block")
        self.assertEqual(clearance.status, "Blocked")

        # The recipient field is fetched from driver.driver_user on save.
        self.assertEqual(clearance.driver_user, self.user)

        self._fire("Salis - Blocked Driver Clearance", clearance)

        self.assertTrue(
            self._driver_logs("Driver Clearance", clearance.name),
            "the blocked driver must receive a Notification Log for their clearance",
        )

    def test_vehicle_compliance_notifies_the_current_driver(self):
        vehicle = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": f"DCL {frappe.generate_hash(length=4).upper()}",
                "status": "Active",
                "current_driver": self.driver,
            }
        ).insert(ignore_permissions=True)

        # current_driver_user is fetched from current_driver.driver_user on save.
        self.assertEqual(vehicle.current_driver_user, self.user)

        self._fire("Salis - Vehicle Compliance Expiring Soon", vehicle)

        self.assertTrue(
            self._driver_logs("Salis Vehicle", vehicle.name),
            "the vehicle's current driver must receive a compliance Notification Log",
        )
