# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Payment Routing Field Map child row.

The child carries no standalone logic; it is exercised in its real parent
context — the Payment Routing Settings single's ``field_map`` table — via an ORM
round-trip that proves each mapping column persists and reads back, and that the
parent's static/source integrity guard sees the rows. Requires a live site."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestPaymentRoutingFieldMap(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_field_map_rows_round_trip(self):
        settings = frappe.get_single("Payment Routing Settings")
        settings.set("field_map", [])
        # A non-static row copies from a source field ...
        settings.append(
            "field_map",
            {"target_fieldname": "party", "source_fieldname": "employee", "is_static": 0},
        )
        # ... a static row carries a literal value (and no source).
        settings.append(
            "field_map",
            {"target_fieldname": "remarks", "is_static": 1, "static_value": "Routed by Apex"},
        )
        settings.save(ignore_permissions=True)

        reloaded = frappe.get_single("Payment Routing Settings")
        rows = {r.target_fieldname: r for r in reloaded.field_map}
        self.assertIn("party", rows)
        self.assertEqual(rows["party"].source_fieldname, "employee")
        self.assertEqual(rows["party"].is_static, 0)
        self.assertEqual(rows["remarks"].is_static, 1)
        self.assertEqual(rows["remarks"].static_value, "Routed by Apex")

    def test_static_row_with_a_source_field_is_rejected_by_parent(self):
        settings = frappe.get_single("Payment Routing Settings")
        settings.set("field_map", [])
        settings.append(
            "field_map",
            {"target_fieldname": "party", "source_fieldname": "employee", "is_static": 1},
        )
        with self.assertRaises(frappe.exceptions.ValidationError):
            settings.save(ignore_permissions=True)
