# Copyright (c) 2026, AFMCO and contributors
"""Tests for the private ``_notify_operational`` / ``_notify_user_system`` helpers
shared by every Habitat scheduled task that posts an operational notice.

``_notify_operational`` is gated by the Habitat Settings "Enable Operational
Notifications" toggle and by having both a source doctype and name; when both
hold it posts a timeline Comment on the source document -- this replaces the
retired Operations Alert inserts, so a silent toggle-off must mean silent, not a
crash, and an on-toggle with no source must not either.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.tasks.common import _notify_operational, _notify_user_system


class TestNotifyOperational(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._toggle = frappe.db.get_single_value(
            "Habitat Settings", "enable_operational_notifications"
        )
        self.addCleanup(self._restore_toggle)
        self.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": f"A564 Notify Test {frappe.generate_hash(length=8)}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)

    def _restore_toggle(self):
        frappe.db.set_single_value(
            "Habitat Settings", "enable_operational_notifications", self._toggle
        )

    def _comment_count(self):
        return frappe.db.count(
            "Comment",
            filters={
                "reference_doctype": "Building",
                "reference_name": self.building.name,
                "comment_type": "Comment",
            },
        )

    def test_toggle_off_posts_nothing(self):
        frappe.db.set_single_value("Habitat Settings", "enable_operational_notifications", 0)
        before = self._comment_count()
        _notify_operational("Building", self.building.name, "should not be posted")
        self.assertEqual(self._comment_count(), before)

    def test_toggle_on_posts_a_timeline_comment_on_the_source(self):
        frappe.db.set_single_value("Habitat Settings", "enable_operational_notifications", 1)
        before = self._comment_count()
        _notify_operational("Building", self.building.name, "A564 marker message")
        self.assertEqual(self._comment_count(), before + 1)

    def test_toggle_on_with_a_blank_source_name_posts_nothing(self):
        frappe.db.set_single_value("Habitat Settings", "enable_operational_notifications", 1)
        before = self._comment_count()
        _notify_operational("Building", "", "should not be posted")
        self.assertEqual(self._comment_count(), before)


class TestNotifyUserSystem(FrappeTestCase):
    def test_a_falsy_user_is_a_no_op_and_does_not_raise(self):
        _notify_user_system(None, "subject that must not be delivered")
        _notify_user_system("", "subject that must not be delivered")
