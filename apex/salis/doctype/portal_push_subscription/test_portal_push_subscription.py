# Copyright (c) 2026, afmcoltd
"""What a Portal Push Subscription guarantees, asserted against the DocType itself.

A Worker subscription must name exactly one employee and no driver; a Driver
subscription must name exactly one driver and no employee. Only an approved
push endpoint is accepted, and the subscription keys are required. One
endpoint may register only once — enforced here in Python (not a DB unique
index) because the ``endpoint`` field is a Small Text/``text`` column, and
Frappe's schema builder silently refuses a unique index on that column type.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Employee", "Salis Driver"]


class TestPortalPushSubscription(FrappeTestCase):
    def test_a_worker_subscription_naming_a_driver_instead_of_an_employee_is_refused(self):
        """A Worker device record must not silently become a driver's."""
        subscription = frappe.copy_doc(frappe.get_test_records("Portal Push Subscription")[0])
        subscription.employee = None
        subscription.driver = "DRV-000001"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Worker notification devices require one employee",
            subscription.insert,
        )

    def test_a_driver_subscription_naming_an_employee_instead_of_a_driver_is_refused(self):
        """A Driver device record must not silently become a worker's."""
        subscription = frappe.copy_doc(frappe.get_test_records("Portal Push Subscription")[1])
        subscription.driver = None
        subscription.employee = "_T-Employee-00001"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Driver notification devices require one driver",
            subscription.insert,
        )

    def test_an_endpoint_outside_the_approved_push_services_is_refused(self):
        """Only recognised push services may receive a subscription; anything else is refused."""
        subscription = frappe.copy_doc(frappe.get_test_records("Portal Push Subscription")[0])
        subscription.endpoint = "https://not-a-real-push-service.example.com/xyz"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "not an approved push service",
            subscription.insert,
        )

    def test_a_second_subscription_for_the_same_endpoint_is_refused(self):
        """A browser re-registering the same endpoint must replace the row, never duplicate it."""
        duplicate = frappe.copy_doc(frappe.get_test_records("Portal Push Subscription")[0])
        self.assertRaisesRegex(
            frappe.DuplicateEntryError,
            "already registered",
            duplicate.insert,
        )
