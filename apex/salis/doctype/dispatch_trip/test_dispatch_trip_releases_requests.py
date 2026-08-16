# Copyright (c) 2026, AFMCO and contributors
"""A trip that ends releases the requests it claimed.

``assign_requests_to_trip`` stamps ``is_assigned`` / ``assigned_to_trip`` on a Transport
Request while the trip is still a Planned DRAFT, and the re-assignment guard then refuses
that request to any other trip. Nothing used to clear either field, and there is no
unassign endpoint — so the documented recovery path (end the trip, re-dispatch the
request) was closed and only a DB-level edit could free the workers on it.

Both exits are graded here because a trip leaves by two doors and only one of them is
cancel: a draft is DELETED, never cancelled, so ``on_cancel`` alone left every abandoned
draft's requests locked to a trip that no longer exists.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.salis.doctype.dispatch_trip.dispatch_trip import assign_requests_to_trip

test_dependencies = ["Salis Vehicle"]


class TestATripReleasesItsRequests(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.project = self._project()
        self.request = self._request()
        self.trip = self._trip()

    def _new(self, doctype, **values):
        doc = frappe.get_doc({"doctype": doctype, **values}).insert(
            ignore_permissions=True, ignore_mandatory=True
        )
        self.addCleanup(self._drop, doctype, doc.name)
        return doc

    @staticmethod
    def _drop(doctype, name):
        if not frappe.db.exists(doctype, name):
            return
        doc = frappe.get_doc(doctype, name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

    def _project(self):
        """Borrowed, never built: ERPNext's Project fixture is not idempotent."""
        existing = frappe.db.get_value("Project", {}, "name")
        if existing:
            return existing
        return self._new(
            "Project", project_name="_DT Project " + frappe.generate_hash(length=12).upper()
        ).name

    def _request(self):
        doc = self._new(
            "Transport Request",
            service_line="Administrative Trip",
            request_type="Administrative Trip / Document Signing",
            destination="_DT Release Destination",
            project=self.project,
            status="New",
        )
        # Placed in the state the workflow would have put it in; the helper under test
        # only accepts an Approved or Scheduled request.
        frappe.db.set_value(
            "Transport Request", doc.name, {"status": "Approved", "docstatus": 1}
        )
        return doc.name

    def _trip(self):
        """Two stops of its own, because the assignment helper derives the pickup and
        drop-off from the trip's own stop keys when the caller names neither."""
        trip = self._new(
            "Dispatch Trip",
            trip_date=today(),
            status="Planned",
            project=self.project,
            stops=[
                {"stop_key": "stop-1", "stop_name": "_DT Pickup"},
                {"stop_key": "stop-2", "stop_name": "_DT Dropoff"},
            ],
        ).name
        assign_requests_to_trip(trip, [{"transport_request": self.request}])
        return trip

    def _claim(self):
        return frappe.db.get_value(
            "Transport Request", self.request, ["is_assigned", "assigned_to_trip"], as_dict=True
        )

    def test_assignment_is_what_puts_the_claim_on(self):
        """Positive control: without this the release assertions could pass on a request
        that was never claimed in the first place."""
        claim = self._claim()
        self.assertEqual(claim.is_assigned, 1)
        self.assertEqual(claim.assigned_to_trip, self.trip)

    def test_deleting_the_draft_trip_releases_the_request(self):
        """A draft never reaches cancel. It is deleted, and the claim has to go with it."""
        frappe.delete_doc("Dispatch Trip", self.trip, force=True, ignore_permissions=True)

        claim = self._claim()
        self.assertEqual(claim.is_assigned, 0, "the request is still claimed by a deleted trip")
        self.assertIsNone(claim.assigned_to_trip)

    def test_the_cancel_reversal_releases_the_request(self):
        """The other door. ``on_cancel`` delegates the whole reversal to this method, and
        it is called directly rather than by driving the trip to Completed and back:
        submitting a Dispatch Trip writes a Trip Fulfilment Ledger, whose naming series
        makes the round trip contend for ``tabseries`` and fail intermittently. What is
        being graded is the reversal, not the workflow that reaches it.

        ``is_assigned`` must come back as an explicit 0, not NULL — NULL is not 0 to the
        filter the re-assignment guard reads.
        """
        frappe.db.set_value(
            "Transport Request",
            self.request,
            {"status": "Fulfilled", "dispatch_trip": self.trip},
        )

        frappe.get_doc("Dispatch Trip", self.trip)._revert_transport_requests()

        claim = self._claim()
        self.assertEqual(claim.is_assigned, 0)
        self.assertIsNone(claim.assigned_to_trip)
        self.assertEqual(
            frappe.db.get_value("Transport Request", self.request, "status"), "Scheduled"
        )

    def test_on_cancel_is_what_runs_that_reversal(self):
        """Guard of the guard: the case above would keep passing if ``on_cancel`` stopped
        calling it, and every cancelled trip would leave its requests locked again."""
        import ast
        import inspect
        import textwrap

        from apex.salis.doctype.dispatch_trip.dispatch_trip import DispatchTrip

        tree = ast.parse(textwrap.dedent(inspect.getsource(DispatchTrip.on_cancel)))
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertIn("_revert_transport_requests", called)

    def test_a_released_request_can_be_claimed_by_another_trip(self):
        """The outcome the two cases above exist for, asserted end to end."""
        frappe.delete_doc("Dispatch Trip", self.trip, force=True, ignore_permissions=True)
        successor = self._new(
            "Dispatch Trip",
            trip_date=today(),
            status="Planned",
            project=self.project,
            stops=[
                {"stop_key": "stop-1", "stop_name": "_DT Pickup"},
                {"stop_key": "stop-2", "stop_name": "_DT Dropoff"},
            ],
        ).name

        assign_requests_to_trip(successor, [{"transport_request": self.request}])

        self.assertEqual(self._claim().assigned_to_trip, successor)
