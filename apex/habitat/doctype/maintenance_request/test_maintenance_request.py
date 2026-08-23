# Copyright (c) 2026, afmcoltd
"""Tests for the Maintenance Request Workflow (apex/fixtures/workflow.json).

Proves the native replacement for the removed ``_guard_status`` hand-throw:
Close/Reopen now travel through ``frappe.model.workflow.apply_workflow``
(the same production path ``close_request``/``reopen_request`` call), and a
status value written any other way — a plain field edit through ``save()`` —
is refused by the framework's own ``validate_workflow``
(frappe/model/document.py:687-695), not by a bespoke ``has_value_changed``
check. Negative control: ``test_a_hand_edited_status_is_refused`` breaks the
old-style bypass on purpose and asserts the exact exception the workflow
raises for it.
"""

from __future__ import annotations

import frappe
from frappe.model.workflow import WorkflowPermissionError
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.maintenance_request.maintenance_request import (
    close_request,
    reopen_request,
)
from apex.tests.factories import make_building, make_maintenance_request, make_room

# ``get_dependencies`` (frappe/test_runner.py:359-381) walks every Link field on
# Maintenance Request, and three of them reach the same unreachable app by three
# separate routes: ``target_asset`` is a direct Link to ERPNext ``Asset``;
# ``related_facility_asset`` -> Facility Asset -> its own ``linked_erpnext_asset``
# reaches the identical ``Asset``; ``subcontractor_service_order`` -> Subcontractor
# Service Order -> Purchase Invoice reaches it a third way. Every route continues
# Asset -> Journal Entry -> Payment Order -> Payment Request -> Payment Gateway
# Account -> Payment Gateway; the payments app is on the bench but not installed
# on this site, so collecting any of these chains aborts the whole suite before a
# single test runs — measured the same way
# habitat/doctype/utility_bill_entry/test_utility_bill_entry.py records it for
# ``Payment Entry``. None of these tests sets ``target_asset``,
# ``related_facility_asset`` or ``subcontractor_service_order``.
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
        """Stand in for Maintenance Work Order's mark_completed db_set (out of
        this test's scope) so the request reaches Resolved without a workflow
        transition — exactly how the app itself reaches this state today."""
        frappe.get_doc("Maintenance Request", self.mr.name).db_set(
            {"status": "Resolved", "resolution_notes": "Leak repaired."}
        )

    def test_a_new_request_defaults_to_open_with_no_python_default(self):
        """The DocType JSON's ``default: Open`` on the status field does this
        alone now that ``_guard_status``'s ``is_new()`` branch is gone."""
        self.assertEqual(self.mr.status, "Open")

    def test_close_then_reopen_travel_through_apply_workflow(self):
        self._resolve()

        close_request(self.mr.name)
        self.assertEqual(frappe.db.get_value("Maintenance Request", self.mr.name, "status"), "Closed")

        reopen_request(self.mr.name, "Leak returned overnight.")
        self.assertEqual(frappe.db.get_value("Maintenance Request", self.mr.name, "status"), "Open")

    def test_a_hand_edited_status_is_refused(self):
        """Break the removed guard's job on purpose: a plain save() that jumps
        the field to a state with no modelled transition from Resolved must
        still fail — now via the Workflow, not a ``has_value_changed`` throw."""
        self._resolve()

        doc = frappe.get_doc("Maintenance Request", self.mr.name)
        doc.status = "In Progress"
        with self.assertRaises(WorkflowPermissionError):
            doc.save()
