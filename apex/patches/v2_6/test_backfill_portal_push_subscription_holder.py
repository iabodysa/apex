# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Portal Push Subscription holder backfill.

The controller now enforces the holder-type XOR on insert (never both driver
and employee), so the pre-migration shape this patch repairs is forced here
through a direct ``db.set_value`` column write, the same way a hand-run SQL
migration once left it.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_6.backfill_portal_push_subscription_holder import execute


def _endpoint():
    return f"https://fcm.googleapis.com/fcm/send/{frappe.generate_hash(length=16)}"


class TestBackfillPortalPushSubscriptionHolder(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.employee = "_T-Employee-00001"
        self.driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": "Backfill Driver " + frappe.generate_hash(length=8),
            }
        ).insert(ignore_permissions=True).name
        self._names = []

    def tearDown(self):
        for name in self._names:
            if frappe.db.exists("Portal Push Subscription", name):
                frappe.delete_doc(
                    "Portal Push Subscription", name, ignore_permissions=True, force=True
                )
        frappe.delete_doc("Salis Driver", self.driver, ignore_permissions=True, force=True)

    def _sub(self):
        doc = frappe.get_doc(
            {
                "doctype": "Portal Push Subscription",
                "holder_type": "Worker",
                "employee": self.employee,
                "endpoint": _endpoint(),
                "p256dh": frappe.generate_hash(length=20),
                "auth": frappe.generate_hash(length=12),
            }
        ).insert(ignore_permissions=True)
        self._names.append(doc.name)
        return doc.name

    def test_a_row_with_a_stray_driver_is_repointed_to_driver_holder(self):
        name = self._sub()
        # Force the pre-guard shape: driver set alongside the Worker holder_type
        # and employee, bypassing the controller the same way old SQL once did.
        frappe.db.set_value("Portal Push Subscription", name, "driver", self.driver)
        frappe.db.commit()

        execute()

        row = frappe.db.get_value(
            "Portal Push Subscription", name, ["holder_type", "employee"], as_dict=True
        )
        self.assertEqual(row.holder_type, "Driver")
        self.assertIsNone(row.employee)

    def test_a_row_with_no_driver_is_left_alone(self):
        name = self._sub()

        execute()

        row = frappe.db.get_value(
            "Portal Push Subscription", name, ["holder_type", "employee"], as_dict=True
        )
        self.assertEqual(row.holder_type, "Worker")
        self.assertEqual(row.employee, self.employee)
