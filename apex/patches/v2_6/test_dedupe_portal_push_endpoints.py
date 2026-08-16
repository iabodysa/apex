# Copyright (c) 2026, AFMCO and contributors
"""Tests for the duplicate-endpoint cleanup patch.

The controller now refuses a SECOND insert for one endpoint, so a duplicate is
forced here the way the real ones landed: through a direct ``db.set_value``
column write, which bypasses the controller the same way the pre-guard
``INSERT`` did. The newest of a duplicated pair must survive; a row that is not
duplicated must be left alone.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_6.dedupe_portal_push_endpoints import execute


def _endpoint():
    return f"https://fcm.googleapis.com/fcm/send/{frappe.generate_hash(length=16)}"


class TestDedupePortalPushEndpoints(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.employee = "_T-Employee-00001"
        self._names = []

    def tearDown(self):
        for name in self._names:
            if frappe.db.exists("Portal Push Subscription", name):
                frappe.delete_doc(
                    "Portal Push Subscription", name, ignore_permissions=True, force=True
                )

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

    def test_only_the_newest_of_a_duplicated_pair_survives(self):
        older = self._sub()
        newer = self._sub()
        shared_endpoint = frappe.db.get_value("Portal Push Subscription", older, "endpoint")
        # Force the pre-guard duplicate state: a direct column write bypasses the
        # controller's own refusal, exactly as the un-indexed column once did.
        frappe.db.set_value("Portal Push Subscription", newer, "endpoint", shared_endpoint)
        frappe.db.commit()

        execute()

        self.assertFalse(frappe.db.exists("Portal Push Subscription", older))
        self.assertTrue(frappe.db.exists("Portal Push Subscription", newer))

    def test_a_row_with_no_duplicate_is_left_alone(self):
        lone = self._sub()

        execute()

        self.assertTrue(frappe.db.exists("Portal Push Subscription", lone))

    def test_a_blank_endpoint_is_never_treated_as_a_duplicate_group(self):
        """The query excludes '' / NULL so unrelated blank rows are not swept together."""
        first = self._sub()
        second = self._sub()
        frappe.db.set_value("Portal Push Subscription", first, "endpoint", "")
        frappe.db.set_value("Portal Push Subscription", second, "endpoint", "")
        frappe.db.commit()

        execute()

        self.assertTrue(frappe.db.exists("Portal Push Subscription", first))
        self.assertTrue(frappe.db.exists("Portal Push Subscription", second))
