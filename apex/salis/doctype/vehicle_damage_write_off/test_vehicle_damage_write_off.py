# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Vehicle Damage Write-Off controller.

Proves the escalation back-link: submitting a write-off raised from a Vehicle
Incident stamps the case onto the incident's read_only write_off_case, and
cancelling clears it, keeping the Incident<->Write-Off link bidirectional.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import frappe
from frappe.model.workflow import apply_workflow, get_workflow_name
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.tests._helpers import _grant_project, _project, _user, submit_via_workflow

WORKFLOW = "Vehicle Damage Write-Off Workflow"


def _make_vehicle(prefix):
    """Create a Salis Vehicle with a per-run-unique plate and return its name.

    These tests commit mid-method (workflow apply / submit), so the vehicle
    escapes FrappeTestCase's savepoint rollback and persists on the test_ignore
    Salis Vehicle table. A deterministic plate therefore trips the
    ``plate_normalized`` unique index against a prior run's residual row
    (the fixed-name variant of the P-216 collision class). A wide random suffix
    keeps every run's fixture distinct from any residual row; ``_purge_fixtures``
    clears them at class teardown so the table does not accumulate.
    """
    return frappe.get_doc(
        {
            "doctype": "Salis Vehicle",
            "plate_number": f"{prefix}-{frappe.generate_hash(length=12)}",
            "status": "Active",
        }
    ).insert(ignore_permissions=True).name


def _purge_fixtures(vehicles, incidents=()):
    """Delete the vehicles/incidents a test class committed. Call from tearDownClass.

    The write-off submit/workflow paths commit, so these rows outlive the
    per-test savepoint. Cleanup runs once at class teardown, not per test: a
    per-test ``frappe.db.commit()`` corrupts FrappeTestCase's per-test savepoint
    (the surrounding class already tolerates a commit here). Write-offs reach
    docstatus 1 and ``delete_doc`` refuses a submitted doc even with force, so
    raw-delete them (the DocType has no child tables to orphan); then the
    incidents and the vehicles, which are docstatus 0.
    """
    frappe.set_user("Administrator")
    for vehicle in vehicles:
        frappe.db.delete("Vehicle Damage Write-Off", {"vehicle": vehicle})
    for incident in incidents:
        if frappe.db.exists("Vehicle Incident", incident):
            frappe.delete_doc("Vehicle Incident", incident, force=True, ignore_permissions=True)
    for vehicle in vehicles:
        if frappe.db.exists("Salis Vehicle", vehicle):
            frappe.delete_doc("Salis Vehicle", vehicle, force=True, ignore_permissions=True)
    frappe.db.commit()


class TestVehicleDamageWriteOff(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._vehicles = []
        cls._incidents = []

    @classmethod
    def tearDownClass(cls):
        # Fixtures escape savepoint rollback (submit/cancel commit); clear them.
        _purge_fixtures(cls._vehicles, cls._incidents)
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")
        # [#99ioui]
        self.vehicle = _make_vehicle("WO")
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
        type(self)._vehicles.append(self.vehicle)
        type(self)._incidents.append(self.incident)

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
        submit_via_workflow(case)
        self.assertEqual(
            frappe.db.get_value("Vehicle Incident", self.incident, "write_off_case"),
            case.name,
            "submit must stamp the case onto the incident's write_off_case",
        )

    def test_cancel_clears_back_link(self):
        case = self._write_off()
        submit_via_workflow(case)
        case.cancel()
        self.assertFalse(
            frappe.db.get_value("Vehicle Incident", self.incident, "write_off_case"),
            "cancel must clear the incident's write_off_case",
        )

    def test_submit_without_source_incident_is_noop(self):
        """No source_incident means on_submit writes to no Vehicle Incident at all.

        Asserting only that this test's own incident stayed unstamped cannot fail:
        with source_incident empty, ``frappe.db.set_value`` would be handed a None
        docname, which it treats as a Single and writes to ``tabSingles`` — no
        Vehicle Incident row moves either way, so removing the guard would keep the
        assertion below green. The falsifiable statement is the count of Vehicle
        Incident writes.
        """
        case = self._write_off(source_incident=None)
        with patch.object(frappe.db, "set_value", wraps=frappe.db.set_value) as writes:
            submit_via_workflow(case)

        self.assertEqual(
            [call.args[:2] for call in writes.call_args_list
             if call.args and call.args[0] == "Vehicle Incident"],
            [],
            "no source_incident means no Vehicle Incident write",
        )
        self.assertFalse(
            frappe.db.get_value("Vehicle Incident", self.incident, "write_off_case"),
            "an unrelated incident must not be touched when no source_incident is set",
        )

    def test_negative_estimated_cost_is_rejected(self):
        # [#srrxvw]
        with self.assertRaises(frappe.ValidationError):
            self._write_off(estimated_cost=-1)

    def test_non_negative_estimated_cost_is_allowed(self):
        # [#17ibxm]
        zero = self._write_off(estimated_cost=0)
        self.assertTrue(zero.name)
        positive = self._write_off(estimated_cost=500)
        self.assertTrue(positive.name)

    def test_needs_operations_derived_from_estimated_cost(self):
        # [#gys5hx]
        frappe.db.set_single_value("Salis Settings", "writeoff_ops_threshold", 2000)
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
        cls._vehicles = []
        cls.supervisor = _user("vwo_sup@example.com", "Fleet Supervisor")
        cls.manager = _user("vwo_doa_mgr@example.com", "Fleet Manager")
        # [#nkqhd1]
        cls.project = _project()
        cls.driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": "VWO DoA Driver",
                "project": cls.project,
            }
        ).insert(ignore_permissions=True).name
        _grant_project(cls.supervisor, cls.project)

    @classmethod
    def tearDownClass(cls):
        # [#aog6ng]
        frappe.set_user("Administrator")
        # Clear committed write-offs + vehicles first so the driver delete is unblocked.
        _purge_fixtures(cls._vehicles)
        frappe.db.delete("User Permission",
                         {"allow": "Project", "for_value": cls.project, "user": cls.supervisor})
        if frappe.db.exists("Salis Driver", cls.driver):
            frappe.delete_doc("Salis Driver", cls.driver, ignore_permissions=True, force=True)
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "writeoff_ops_threshold", 2000)
        # [#h8la3d]
        self.vehicle = _make_vehicle("WD")
        type(self)._vehicles.append(self.vehicle)

    def tearDown(self):
        frappe.set_user("Administrator")

    def _case(self, estimated_cost):
        # [#b6z7yk]
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
