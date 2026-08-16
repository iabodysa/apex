# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Payment Routing Settings controller's ``validate`` wiring.

``apex.apex_core.payment_router.validate_target_doctype`` / ``validate_field_map``
already have their own dedicated, thorough tests (``test_payment_router.py``), which
deliberately plant an invalid config with ``db_set`` to prove the ROUTER refuses at
build time even when the controller is bypassed. What neither of those proves is
that this controller's own ``validate()`` actually calls them on an ordinary save --
that a config-time typo is caught at config time, not just at first use. This test
proves the wiring: an invalid target refuses ON SAVE, a valid one does not.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestPaymentRoutingSettings(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.doc = frappe.get_single("Payment Routing Settings")
        self._target = self.doc.target_payment_doctype
        self._field_map = [dict(row.as_dict()) for row in self.doc.field_map]
        self.addCleanup(self._restore)

    def _restore(self):
        doc = frappe.get_single("Payment Routing Settings")
        doc.target_payment_doctype = self._target
        doc.set("field_map", self._field_map)
        doc.save(ignore_permissions=True)

    def test_save_with_a_single_doctype_target_is_refused_at_save_time(self):
        """Habitat Settings is a real, installed Single -- structurally impossible
        as a payment target (insert would overwrite tabSingles, not create a row)."""
        self.doc.target_payment_doctype = "Habitat Settings"
        with self.assertRaises(frappe.ValidationError):
            self.doc.save(ignore_permissions=True)

    def test_save_with_an_uninstalled_doctype_target_is_refused_at_save_time(self):
        self.doc.target_payment_doctype = "Not A Real DocType XYZ"
        with self.assertRaises(frappe.ValidationError):
            self.doc.save(ignore_permissions=True)

    def test_save_with_a_valid_target_and_empty_field_map_is_accepted(self):
        self.doc.target_payment_doctype = "Note"
        self.doc.set("field_map", [])
        self.doc.save(ignore_permissions=True)  # must not raise
        self.assertEqual(self.doc.target_payment_doctype, "Note")

    def test_save_with_a_field_map_row_naming_a_nonexistent_target_field_is_refused(self):
        self.doc.target_payment_doctype = "Note"
        self.doc.set(
            "field_map",
            [{"target_fieldname": "this_field_does_not_exist_on_note", "is_static": 1, "static_value": "x"}],
        )
        with self.assertRaises(frappe.ValidationError):
            self.doc.save(ignore_permissions=True)
