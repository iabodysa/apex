# Copyright (c) 2026, AFMCO and contributors
"""the Habitat expiry-watcher notify boilerplate was replaced by native
``is_standard`` Notifications. This locks in that the six records ship enabled and
correctly wired (document type, event, date field), so migrate exports + imports them
and the daily notification scheduler picks them up.

Recipient resolution and firing are the framework's own tested paths; here we assert
the declarative shape (the thing the refactor is responsible for) plus that each
firing ``condition`` gates on the intended document state via ``frappe.safe_eval``,
mirroring test_fleet_alert_notifications.
"""

import frappe
from frappe.tests.utils import FrappeTestCase


# name -> (document_type, event, date_changed, days_in_advance)
_EXPIRY_NOTIFICATIONS = {
    "Habitat - Building License Expiring Soon": ("Building License", "Days Before", "expiry_date", 60),
    "Habitat - Building License Expired": ("Building License", "Days Before", "expiry_date", 0),
    "Habitat - Building Lease Expiring": ("Lease", "Days Before", "lease_end_date", 90),
    "Habitat - Building Lease Expired": ("Lease", "Days Before", "lease_end_date", 0),
    "Habitat - Temporary Stay Ending": ("Housing Assignment", "Days Before", "expected_checkout_date", 2),
    "Habitat - Temporary Stay Overdue": ("Housing Assignment", "Days After", "expected_checkout_date", 1),
}


class TestHabitatExpiryNotifications(FrappeTestCase):
    def test_records_are_synced_and_enabled(self):
        """All six load on a fresh site, is_standard + enabled, with the expected
        date-field wiring the daily notification runner keys on."""
        for name, (doctype, event, date_field, days) in _EXPIRY_NOTIFICATIONS.items():
            n = frappe.get_doc("Notification", name)
            self.assertEqual(n.is_standard, 1, f"{name} must be is_standard")
            self.assertEqual(n.enabled, 1, f"{name} must ship enabled")
            self.assertEqual(n.document_type, doctype, f"{name} document_type")
            self.assertEqual(n.event, event, f"{name} event")
            self.assertEqual(n.date_changed, date_field, f"{name} date_changed")
            self.assertEqual(n.days_in_advance, days, f"{name} days_in_advance")
            self.assertTrue(n.recipients, f"{name} must resolve at least one recipient")

    def test_temporary_stay_condition_gates_on_temporary_open_stay(self):
        """The temporary-stay alerts fire only for a submitted Temporary stay that is
        still checked in (no check_out_date) — not a permanent or a checked-out one."""
        for name in ("Habitat - Temporary Stay Ending", "Habitat - Temporary Stay Overdue"):
            condition = frappe.get_doc("Notification", name).condition
            live = frappe._dict(docstatus=1, stay_type="Temporary", check_out_date=None)
            permanent = frappe._dict(docstatus=1, stay_type="Permanent", check_out_date=None)
            checked_out = frappe._dict(docstatus=1, stay_type="Temporary", check_out_date="2026-01-01")
            self.assertTrue(frappe.safe_eval(condition, None, {"doc": live}), f"{name} must fire on a live temporary stay")
            self.assertFalse(frappe.safe_eval(condition, None, {"doc": permanent}), f"{name} must not fire on a permanent stay")
            self.assertFalse(frappe.safe_eval(condition, None, {"doc": checked_out}), f"{name} must not fire once checked out")

    def test_license_expiring_condition_gates_on_live_status(self):
        """The Building License Expiring Soon alert fires only for a submitted license
        that is still Active / Expiring Soon (mirrors the residual status sweep filter)."""
        condition = frappe.get_doc("Notification", "Habitat - Building License Expiring Soon").condition
        active = frappe._dict(docstatus=1, status="Active")
        revoked = frappe._dict(docstatus=1, status="Revoked")
        self.assertTrue(frappe.safe_eval(condition, None, {"doc": active}))
        self.assertFalse(frappe.safe_eval(condition, None, {"doc": revoked}))
