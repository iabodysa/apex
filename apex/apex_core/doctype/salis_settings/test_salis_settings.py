# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Salis Settings zero-trap read helpers.

A new Int/Float on an existing Single stores 0 (not its JSON default), so every
numeric read must coalesce a blank/0 value to the caller's default. These tests
pin that behaviour for the canonical get_salis_int / get_salis_float helpers and
for the extracted thresholds that now route through them — proving no caller
trusts a raw 0.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.salis_settings.salis_settings import (
    get_salis_float,
    get_salis_int,
)


class TestSalisSettingsHelpers(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_int_returns_default_when_unset_not_zero(self):
        # [#k0y30s]
        frappe.db.set_single_value("Salis Settings", "admin_trip_ops_threshold", 0)
        self.assertEqual(get_salis_int("admin_trip_ops_threshold", 5), 5)

    def test_int_returns_stored_nonzero_value(self):
        frappe.db.set_single_value("Salis Settings", "admin_trip_ops_threshold", 9)
        self.assertEqual(get_salis_int("admin_trip_ops_threshold", 5), 9)

    def test_float_returns_default_when_unset_not_zero(self):
        frappe.db.set_single_value("Salis Settings", "writeoff_ops_threshold", 0)
        self.assertEqual(get_salis_float("writeoff_ops_threshold", 2000.0), 2000.0)

    def test_float_returns_stored_nonzero_value(self):
        frappe.db.set_single_value("Salis Settings", "writeoff_ops_threshold", 3500)
        self.assertEqual(get_salis_float("writeoff_ops_threshold", 2000.0), 3500.0)

    def test_license_expiring_warn_days_default(self):
        frappe.db.set_single_value("Salis Settings", "license_expiring_warn_days", 0)
        self.assertEqual(get_salis_int("license_expiring_warn_days", 30), 30)

    def test_fuel_overage_margin_reads_via_helper(self):
        # [#lvkez3]
        from apex.salis.fuel_engine import get_overage_margin

        frappe.db.set_single_value("Salis Settings", "fuel_overage_margin_percent", 0)
        self.assertAlmostEqual(get_overage_margin(), 0.05)
        frappe.db.set_single_value("Salis Settings", "fuel_overage_margin_percent", 10)
        self.assertAlmostEqual(get_overage_margin(), 0.10)
