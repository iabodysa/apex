# Copyright (c) 2026, AFMCO and contributors
"""A Movement document may advance a Transport Request. It may not submit one.

``drive_transport_request`` is called from ``RoutePlan.on_submit`` and
``DispatchTrip.on_submit``. When the acting user does not personally hold the workflow
transition, it falls back to a direct write so the operational chain does not deadlock
on a permission gap.

A fallback that carries its own private copy of the Workflow's own state -> doc_status
table, writing ``docstatus`` from it directly, lets a Fleet Manager who raises a
Transport Request themselves — and whose self-approval the workflow's own
Segregation-of-Duties condition refuses — create a Route Plan naming it, submit the
plan, and land the request at Scheduled / docstatus 1: authorized and submitted by its
own requester, with no Authorize transition executed, no Workflow Action row and no
``before_submit`` re-check. An explicitly Rejected request goes the same way.

The fallback now writes ``status`` and nothing else, and only from a state the Workflow
itself lists as a source for that action.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.utils import drive_transport_request, revert_transport_request


class TestTransportRequestDrive(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def _request(self, status="New"):
        doc = frappe.get_doc(
            {
                "doctype": "Transport Request",
                "service_line": "Administrative Trip",
                "request_type": "Administrative Trip / Document Signing",
                "destination": "_TR Drive Destination",
                "status": "New",
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(self._drop, doc.name)
        if status != "New":
            frappe.db.set_value(
                "Transport Request",
                doc.name,
                {"status": status, "docstatus": _DOCSTATUS_OF[status]},
            )
        return doc.name

    @staticmethod
    def _drop(name):
        """The fixture is placed in its state by a direct write, so it is taken out of
        one the same way — the framework refuses to delete a docstatus 1 row."""
        frappe.db.set_value("Transport Request", name, "docstatus", 0)
        frappe.delete_doc("Transport Request", name, force=True, ignore_permissions=True)

    def _row(self, name):
        return frappe.db.get_value(
            "Transport Request", name, ["status", "docstatus"], as_dict=True
        )

    def test_a_request_that_was_never_authorized_is_not_submitted_by_a_route_plan(self):
        """The defect. New -> Scheduled skips Validate and both Authorize transitions."""
        name = self._request("New")

        result = drive_transport_request(name, action="Schedule", target_state="Scheduled")

        row = self._row(name)
        self.assertIsNone(result)
        self.assertEqual(row.status, "New", "the request advanced without its transition")
        self.assertEqual(row.docstatus, 0, "a direct write submitted the request")

    def test_a_rejected_request_is_not_revived_by_a_route_plan(self):
        """Worse than the reported case: Rejected is not terminal to this helper, so the
        force-write drove an explicitly refused request to Scheduled / docstatus 1."""
        name = self._request("Rejected")

        result = drive_transport_request(name, action="Schedule", target_state="Scheduled")

        row = self._row(name)
        self.assertIsNone(result)
        self.assertEqual(row.status, "Rejected")
        self.assertEqual(row.docstatus, 0)

    def test_a_validated_request_still_needs_its_authorization(self):
        """Validated is a source for Authorize, not for Schedule."""
        name = self._request("Validated")

        result = drive_transport_request(name, action="Schedule", target_state="Scheduled")

        self.assertIsNone(result)
        self.assertEqual(self._row(name).status, "Validated")

    def test_an_approved_request_is_advanced_without_touching_docstatus(self):
        """The fallback the helper exists for. Approved is the Workflow's own source for
        Schedule, and both states are doc_status 1 — so there is nothing to write."""
        name = self._request("Approved")

        result = drive_transport_request(
            name, action="Schedule", target_state="Scheduled", extra_fields={"route_plan": None}
        )

        row = self._row(name)
        self.assertEqual(result, "Scheduled")
        self.assertEqual(row.status, "Scheduled")
        self.assertEqual(row.docstatus, 1, "the source state's docstatus was disturbed")

    def test_the_reversal_leaves_docstatus_where_the_workflow_put_it(self):
        """Scheduled <- Fulfilled are both doc_status 1; the reversal writes status only."""
        name = self._request("Fulfilled")

        result = revert_transport_request(name, from_state="Fulfilled", to_state="Scheduled")

        row = self._row(name)
        self.assertEqual(result, "Scheduled")
        self.assertEqual(row.status, "Scheduled")
        self.assertEqual(row.docstatus, 1)

    def test_the_source_states_come_from_the_workflow_record(self):
        """Positive control: the states are read off the shipped Workflow, not a copy in
        the module. A workflow that stopped defining Schedule would empty this set and
        every case above would refuse for the wrong reason."""
        from apex.salis.utils import _workflow_source_states

        self.assertEqual(_workflow_source_states("Schedule"), {"Approved"})
        self.assertEqual(_workflow_source_states("Confirm Fulfilment"), {"Scheduled"})


# The Workflow's own state -> doc_status table, used only to PLACE a fixture in a state
# the workflow would have put it in. The application code no longer holds a copy.
_DOCSTATUS_OF = {
    "New": 0,
    "Validated": 0,
    "Approved": 1,
    "Scheduled": 1,
    "Fulfilled": 1,
    "Rejected": 0,
    "Cancelled": 2,
}
