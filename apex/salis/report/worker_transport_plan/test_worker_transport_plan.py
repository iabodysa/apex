# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Worker Transport Plan report execute().

Asserts the column contract and that execute() runs end-to-end (service-line
scoped, project scope unrestricted for Administrator) returning a data list whose
rows carry every declared field. Requires a live site (queries Transport
Request).

The row test seeds a Site Transport request carrying a worker manifest: on an
empty test database the per-row loop had nothing to iterate, so the row-shape
assertion never executed and the service-line scope went unproven."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

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
        tag = frappe.generate_hash(length=12).upper()
        company = frappe.db.get_value("Company", {})

        self.project = frappe.get_doc(
            {"doctype": "Project", "project_name": f"WTP Project {tag}"}
        ).insert(ignore_permissions=True).name
        self.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": f"WTP Bldg {tag}",
                "status": "Active",
                "total_capacity": 10,
            }
        ).insert(ignore_permissions=True).name
        employee = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": f"WTP Worker {tag}",
                "company": company,
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
            }
        ).insert(ignore_permissions=True).name

        # A Site Transport shuttle is exactly what the report scopes to; the
        # Administrative Trip line below must stay out of the result.
        self.request = frappe.get_doc(
            {
                "doctype": "Transport Request",
                "service_line": "Site Transport",
                "request_type": "Accommodation to Project Shuttle",
                "project": self.project,
                "accommodation_building": self.building,
                "from_location": self.building,
                "to_location": "Project Site",
                "source_channel": "Desk",
                "status": "New",
                "pickup_datetime": add_to_date(now_datetime(), hours=6),
                "workers": [{"employee": employee, "pickup_point": "Building Gate"}],
            }
        ).insert(ignore_permissions=True).name

        self.admin_trip = frappe.get_doc(
            {
                "doctype": "Transport Request",
                "service_line": "Administrative Trip",
                "request_type": "Administrative Trip / Document Signing",
                "project": self.project,
                "destination": "Client head office",
                "source_channel": "Desk",
                "status": "New",
            }
        ).insert(ignore_permissions=True).name

    def test_columns_contract(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data = execute({})
        self.assertTrue(data, "The seeded transport request must reach the report.")

        checked = 0
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
            checked += 1
        self.assertEqual(
            checked, len(data), "The per-row assertions must run for every row."
        )

    def test_only_worker_carrying_service_lines_are_planned(self):
        _columns, data = execute({})
        by_name = {row["name"]: row for row in data}

        self.assertIn(self.request, by_name, "A Site Transport request must be planned.")
        self.assertNotIn(
            self.admin_trip,
            by_name,
            "An Administrative Trip carries no worker manifest and must stay out of "
            "the worker transport plan.",
        )
        row = by_name[self.request]
        self.assertEqual(row["project"], self.project)
        self.assertEqual(row["accommodation_building"], self.building)
        # worker_count is derived server-side from the manifest, never sent by the form.
        self.assertEqual(row["worker_count"], 1)
