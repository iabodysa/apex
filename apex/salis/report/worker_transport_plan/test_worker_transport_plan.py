# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Worker Transport Plan report execute().

Asserts the column contract and that execute() runs end-to-end (service-line
scoped, project scope unrestricted for Administrator) returning a data list whose
rows carry every declared field. Requires a live site (queries Transport
Request)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.report.worker_transport_plan.worker_transport_plan import execute

_EXPECTED_FIELDS = [
    "name",
    "request_type",
    "accommodation_building",
    "project",
    "worker_count",
    "is_cross_region",
    "pickup_datetime",
    "status",
    "assigned_vehicle",
    "assigned_driver",
]


class TestWorkerTransportPlan(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_columns_contract(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data = execute({})
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
