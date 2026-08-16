# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Portal Push Subscription controller.

Asserts the endpoint's declared uniqueness and the holder-type XOR: a Worker
subscription resolves to exactly one Employee holder, a Driver subscription to
exactly one Salis Driver holder — never both, never neither.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _endpoint():
    return f"https://fcm.googleapis.com/fcm/send/{frappe.generate_hash(length=16)}"


class TestPortalPushSubscription(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.employee = "_T-Employee-00001"
        self.driver = "DRV-000001"
        self._created = []
        self.addCleanup(self._purge)

    def _purge(self):
        frappe.set_user("Administrator")
        for name in self._created:
            if frappe.db.exists("Portal Push Subscription", name):
                frappe.delete_doc(
                    "Portal Push Subscription", name, ignore_permissions=True, force=True
                )

    def _sub(self, **overrides):
        data = {
            "doctype": "Portal Push Subscription",
            "holder_type": "Worker",
            "employee": self.employee,
            "endpoint": _endpoint(),
            "p256dh": "test-p256dh-key",
            "auth": "test-auth-secret",
        }
        data.update(overrides)
        return frappe.get_doc(data)

    def _insert(self, doc):
        doc.insert(ignore_permissions=True)
        self._created.append(doc.name)
        return doc

    def test_two_subscriptions_cannot_share_endpoint(self):
        """Two rows may not hold one endpoint, though no index enforces it.

        The field is Small Text, which maps to a MySQL text column, and the schema builder
        skips a unique index on text (frappe/database/schema.py:212) even where one is
        declared. The controller carries the guarantee instead.
        """
        shared = _endpoint()
        self._insert(self._sub(endpoint=shared))

        second = self._sub(
            endpoint=shared, holder_type="Driver", employee=None, driver=self.driver
        )
        with self.assertRaises(frappe.DuplicateEntryError):
            self._insert(second)

    def test_worker_subscription_resolves_to_employee_only(self):
        # Worker with a driver ALSO set must be refused — not two holders at once.
        with self.assertRaises(frappe.ValidationError):
            self._sub(driver=self.driver).insert(ignore_permissions=True)
        # Worker with no employee must be refused — not zero holders either.
        with self.assertRaises(frappe.ValidationError):
            self._sub(employee=None).insert(ignore_permissions=True)
        # Exactly one holder (employee only) is accepted.
        ok = self._insert(self._sub())
        self.assertEqual(ok.employee, self.employee)
        self.assertFalse(ok.driver)

    def test_driver_subscription_resolves_to_driver_only(self):
        # Driver with an employee ALSO set must be refused — not two holders at once.
        with self.assertRaises(frappe.ValidationError):
            self._sub(holder_type="Driver", driver=self.driver).insert(ignore_permissions=True)
        # Driver with no driver set must be refused — not zero holders either.
        with self.assertRaises(frappe.ValidationError):
            self._sub(holder_type="Driver", employee=None).insert(ignore_permissions=True)
        # Exactly one holder (driver only) is accepted.
        ok = self._insert(self._sub(holder_type="Driver", employee=None, driver=self.driver))
        self.assertEqual(ok.driver, self.driver)
        self.assertFalse(ok.employee)
