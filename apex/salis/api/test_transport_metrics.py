# Copyright (c) 2026, AFMCO and contributors
"""Tests for the transport-requests-served percentage API.

Asserts the docstring's contract: the percentage of THIS MONTH's Transport
Requests that got a trip (a non-reversed Trip Fulfilment Ledger row), scoped by
project for a project-scoped caller.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.salis.api.transport_metrics import get_transport_requests_served_pct
from apex.tests._helpers import _grant_project, _project, _user


class TestTransportRequestsServedPct(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = _project(f"TM Scope Project {frappe.generate_hash(length=12)}")
        cls.supervisor = _user("tm_metrics_sup@example.com", "Fleet Supervisor")
        _grant_project(cls.supervisor, cls.project)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete(
            "User Permission",
            {"allow": "Project", "for_value": cls.project, "user": cls.supervisor},
        )
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def _request(self, served):
        tr = frappe.get_doc(
            {
                "doctype": "Transport Request",
                "service_line": "Administrative Trip",
                "request_type": "Administrative Trip / Document Signing",
                "destination": "Test HQ",
                "project": self.project,
                "pickup_datetime": today(),
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Transport Request", tr.name, ignore_permissions=True, force=True
            )
        )
        if served:
            ledger = frappe.get_doc(
                {"doctype": "Trip Fulfilment Ledger", "transport_request": tr.name}
            ).insert(ignore_permissions=True)
            self.addCleanup(
                lambda: frappe.delete_doc(
                    "Trip Fulfilment Ledger", ledger.name, ignore_permissions=True, force=True
                )
            )
        return tr.name

    def test_served_percentage_scoped_by_project(self):
        self._request(served=True)
        self._request(served=False)

        frappe.set_user(self.supervisor)
        try:
            result = get_transport_requests_served_pct()
        finally:
            frappe.set_user("Administrator")

        self.assertEqual(result["value"], 50.0)
        self.assertEqual(result["fieldtype"], "Percent")

    def test_user_with_no_allowed_project_reports_full_service(self):
        """``restrict=True`` and ``allowed=[]`` — a scoped role holding no Project
        User Permission at all sees the vacuous "nothing to see, nothing unserved"
        100% branch, never a division by zero."""
        unscoped_supervisor = _user("tm_metrics_noproj@example.com", "Fleet Supervisor")
        frappe.set_user(unscoped_supervisor)
        try:
            result = get_transport_requests_served_pct()
        finally:
            frappe.set_user("Administrator")

        self.assertEqual(result["value"], 100.0)
