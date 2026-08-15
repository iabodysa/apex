# Copyright (c) 2026, AFMCO and contributors
"""Driver-facing Salis notification wiring.

Proves that the Blocked Driver Clearance notification resolves to the affected driver's
own User and drops a Notification Log row for that driver.

The companion case for "Vehicle Compliance Expiring Soon" lives beside the writer that
fills its recipient, in
``salis/doctype/vehicle_assignment/test_vehicle_assignment_driver_mirror.py``. That
notification addresses ``Salis Vehicle.current_driver_user``, a fetch_from mirror of
``current_driver.driver_user``, and the sanctioned writers of the pairing all use
``frappe.db.set_value``, which runs no controller and no fetch — so the mirror is
stamped explicitly by ``salis.utils.set_current_driver`` rather than left to the
framework.

The driver's User is reached through a denormalised single-hop fetch chain
(Salis Driver.driver_user <- employee.user_id; the source docs mirror it),
because Notification recipients read a flat local field and validate it as an
email, and ``receiver_by_document_field`` cannot walk a dotted cross-doc path.

The in-app delivery (Notification Log) is exercised through
``create_system_notification`` — the System Notification channel both alerts
ship — so the assertion does not depend on a configured outgoing mail server.

The whole identity chain is borrowed rather than built: the rider and the vehicle are the
Salis fixtures, and the employee behind them is ERPNext's own, whose ``user_id`` is the
portal account the mirror has to land. The single link written onto the borrowed rider is
cleared again after each case.
"""

from __future__ import annotations

import frappe
from frappe.email.doctype.notification.notification import get_context
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Driver", "Employee"]

DRIVER_NAME = "_Test Driver"
WORKER = "_Test Employee"
# The portal account ERPNext's _Test Employee fixture carries in user_id.
PORTAL_USER = "test@example.com"


class TestDriverClearanceNotification(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.user = PORTAL_USER
        self.employee = frappe.db.get_value("Employee", {"first_name": WORKER})
        self.driver = frappe.db.get_value("Salis Driver", {"full_name": DRIVER_NAME}, "name")

        self.addCleanup(self._restore)
        driver_doc = frappe.get_doc("Salis Driver", self.driver)
        driver_doc.employee = self.employee
        driver_doc.save(ignore_permissions=True)

    def _restore(self):
        frappe.db.set_value(
            "Salis Driver", self.driver, {"employee": None, "driver_user": None}
        )

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
        clearance = apply_workflow(clearance, "Block")
        self.assertEqual(clearance.status, "Blocked")

        self.assertEqual(clearance.driver_user, self.user)

        self._fire("Salis - Blocked Driver Clearance", clearance)

        self.assertTrue(
            self._driver_logs("Driver Clearance", clearance.name),
            "the blocked driver must receive a Notification Log for their clearance",
        )

