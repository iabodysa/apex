# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.model.workflow import WorkflowPermissionError, apply_workflow
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.maintenance_request.maintenance_request import (
    close_request,
    reopen_request,
)
from apex.tests.factories import make_building, make_maintenance_request, make_room

test_ignore = ["Asset", "Facility Asset", "Subcontractor Service Order"]


class TestMaintenanceRequestWorkflow(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        building = make_building("MR Workflow Test Building", company="_Test Company")
        room = make_room(building.name)
        self.mr = make_maintenance_request(building.name, room.name)
        self.addCleanup(self._delete_request)

    def _delete_request(self):
        doc = frappe.get_doc("Maintenance Request", self.mr.name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Maintenance Request", self.mr.name, force=True)

    def _resolve(self):
        doc = frappe.get_doc("Maintenance Request", self.mr.name)
        apply_workflow(doc, "Start Processing")
        apply_workflow(doc, "Resolve")

    def test_a_new_request_defaults_to_open_with_no_python_default(self):
        self.assertEqual(self.mr.status, "Open")

    def test_open_reaches_resolved_through_declared_transitions(self):
        doc = frappe.get_doc("Maintenance Request", self.mr.name)
        apply_workflow(doc, "Start Processing")
        self.assertEqual(
            frappe.db.get_value("Maintenance Request", self.mr.name, "status"), "In Progress"
        )

        apply_workflow(frappe.get_doc("Maintenance Request", self.mr.name), "Resolve")
        self.assertEqual(
            frappe.db.get_value("Maintenance Request", self.mr.name, "status"), "Resolved"
        )

    def test_close_then_reopen_travel_through_apply_workflow(self):
        self._resolve()

        close_request(self.mr.name)
        self.assertEqual(frappe.db.get_value("Maintenance Request", self.mr.name, "status"), "Closed")

        reopen_request(self.mr.name, "Leak returned overnight.")
        self.assertEqual(frappe.db.get_value("Maintenance Request", self.mr.name, "status"), "Open")

    def test_a_hand_edited_status_is_refused(self):
        self._resolve()

        doc = frappe.get_doc("Maintenance Request", self.mr.name)
        doc.status = "In Progress"
        with self.assertRaises(WorkflowPermissionError):
            doc.save()
