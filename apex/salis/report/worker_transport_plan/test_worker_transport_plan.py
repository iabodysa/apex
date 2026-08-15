# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Worker Transport Plan report execute().

Asserts the column contract and that execute() runs end-to-end (service-line
scoped, project scope unrestricted for Administrator) returning a data list whose
rows carry every declared field. Requires a live site (queries Transport
Request).

The row test seeds a Site Transport request carrying a worker manifest: on an
empty test database the per-row loop had nothing to iterate, so the row-shape
assertion never executed and the service-line scope went unproven. The building
and the worker on that manifest come from the shipped fixtures — only the two
Transport Requests, which are what the report scopes, are built here.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from apex.salis.report.worker_transport_plan.worker_transport_plan import execute

# Project is deliberately NOT a dependency. ERPNext's Project fixture is not idempotent —
# its autoname mints a new name while project_name carries a unique index, so a second
# build attempt collides instead of being skipped. The request only needs a project id, so
# the one already on the site is read rather than rebuilt.
test_dependencies = ["Building", "Employee"]

BUILDING = "_Test Building"
WORKER = "_Test Employee"

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
        self.project = frappe.db.get_value("Project", {"project_name": "_Test Project"})
        self.building = BUILDING
        employee = frappe.db.get_value("Employee", {"first_name": WORKER})

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
        columns, data, *_rest = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data, *_rest = execute({})
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
        _columns, data, *_rest = execute({})
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
