# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Vehicle Damage Write-Off controller.

Proves the escalation back-link: submitting a write-off raised from a Vehicle
Incident stamps the case onto the incident's read_only write_off_case, and
cancelling clears it, keeping the Incident<->Write-Off link bidirectional.
"""

from __future__ import annotations

import unittest

import frappe
from frappe.model.workflow import apply_workflow, get_workflow_name
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex_habitat.tests._helpers import _grant_project, _project, _user

WORKFLOW = "Vehicle Damage Write-Off Workflow"


class TestVehicleDamageWriteOff(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName
        self.vehicle = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": f"WO {tag}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name
        self.incident = frappe.get_doc(
            {
                "doctype": "Vehicle Incident",
                "incident_type": "Accident",
                "vehicle": self.vehicle,
                "incident_date": today(),
                "description": "Test incident",
                "fault": "Third party",
            }
        ).insert(ignore_permissions=True).name

    def _write_off(self, **overrides):
        data = {
            "doctype": "Vehicle Damage Write-Off",
            "vehicle": self.vehicle,
            "source_incident": self.incident,
            "estimated_cost": 1000,
            "evidence": "/files/evidence.pdf",
        }
        data.update(overrides)
        return frappe.get_doc(data).insert(ignore_permissions=True)

    def test_submit_stamps_back_link_on_source_incident(self):
        case = self._write_off()
        self.assertFalse(
            frappe.db.get_value("Vehicle Incident", self.incident, "write_off_case"),
            "the back-link must be empty before submit",
        )
        case.submit()
        self.assertEqual(
            frappe.db.get_value("Vehicle Incident", self.incident, "write_off_case"),
            case.name,
            "submit must stamp the case onto the incident's write_off_case",
        )

    def test_cancel_clears_back_link(self):
        case = self._write_off()
        case.submit()
        case.cancel()
        self.assertFalse(
            frappe.db.get_value("Vehicle Incident", self.incident, "write_off_case"),
            "cancel must clear the incident's write_off_case",
        )

    def test_submit_without_source_incident_is_noop(self):
        case = self._write_off(source_incident=None)
        case.submit()
        self.assertFalse(
            frappe.db.get_value("Vehicle Incident", self.incident, "write_off_case"),
            "an unrelated incident must not be touched when no source_incident is set",
        )

    def test_negative_estimated_cost_is_rejected(self):
        # a negative estimated cost is never a valid write-off amount.
        with self.assertRaises(frappe.ValidationError):
            self._write_off(estimated_cost=-1)

    def test_non_negative_estimated_cost_is_allowed(self):
        # Non-vacuous: the guard rejects only negatives; zero and positive pass.
        zero = self._write_off(estimated_cost=0)
        self.assertTrue(zero.name)
        positive = self._write_off(estimated_cost=500)
        self.assertTrue(positive.name)

    def test_needs_operations_derived_from_estimated_cost(self):
        # The Write-Off Operations Threshold is REAL: needs_operations is derived
        # server-side from estimated_cost vs the threshold (was a dead setting).
        frappe.db.set_single_value("Salis Settings", "writeoff_ops_threshold_sar", 2000)
        below = self._write_off(estimated_cost=1999)
        self.assertEqual(below.needs_operations, 0)
        at = self._write_off(estimated_cost=2000)
        self.assertEqual(at.needs_operations, 1)


@unittest.skipUnless(
    get_workflow_name("Vehicle Damage Write-Off") == WORKFLOW,
    "Vehicle Damage Write-Off Workflow not seeded on this site",
)
class TestVehicleDamageWriteOffDoA(FrappeTestCase):
    """Delegation-of-Authority tier gate: a write-off whose estimated cost reaches
    the Write-Off Operations Threshold needs Operations-tier authority (Fleet
    Manager); below it Regional-tier (Fleet Supervisor) suffices."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supervisor = _user("vwo_sup@example.com", "Fleet Supervisor")
        cls.manager = _user("vwo_doa_mgr@example.com", "Fleet Manager")
        # The write-off is project-scoped (vehicle_damage_write_off_has_permission
        # resolves the project via driver -> Salis Driver). Fleet Supervisor is a
        # SCOPED role, so the regional authorizer must be permitted for the case's
        # project for the project-scope gate to admit it — without this the DoA tier
        # gate (the actual subject here) can never be reached. Fleet Manager is an
        # UNSCOPED oversight role and needs no Project User Permission.
        cls.project = _project()
        cls.driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": "VWO DoA Driver",
                "project": cls.project,
            }
        ).insert(ignore_permissions=True).name
        _grant_project(cls.supervisor, cls.project)

    def setUp(self):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "writeoff_ops_threshold_sar", 2000)
        self.vehicle = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": f"WD {self._testMethodName}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name

    def tearDown(self):
        frappe.set_user("Administrator")

    def _case(self, estimated_cost):
        # Owned by Administrator so the approver (supervisor/manager) is never the owner.
        case = frappe.get_doc(
            {
                "doctype": "Vehicle Damage Write-Off",
                "vehicle": self.vehicle,
                "driver": self.driver,
                "estimated_cost": estimated_cost,
                "evidence": "/files/evidence.pdf",
                "damage_description": "Test damage",
            }
        ).insert(ignore_permissions=True)
        apply_workflow(case, "Submit for Review")
        case.reload()
        return case

    def test_gate_fires_above_threshold_for_regional_user(self):
        case = self._case(estimated_cost=5000)
        frappe.set_user(self.supervisor)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(case, "Authorize (Regional)")
        case.reload()
        self.assertEqual(case.docstatus, 0)
        self.assertEqual(case.status, "Under Review")

    def test_gate_passes_below_threshold_for_regional_user(self):
        case = self._case(estimated_cost=500)
        frappe.set_user(self.supervisor)
        apply_workflow(case, "Authorize (Regional)")
        case.reload()
        self.assertEqual(case.docstatus, 1)
        self.assertEqual(case.status, "Approved")

    def test_operations_user_passes_above_threshold(self):
        case = self._case(estimated_cost=5000)
        frappe.set_user(self.manager)
        apply_workflow(case, "Authorize (Operations)")
        case.reload()
        self.assertEqual(case.docstatus, 1)
        self.assertEqual(case.status, "Approved")
