# Copyright (c) 2026, AFMCO and contributors
"""Native Workflow tests for Transport Request (the Workflow Spine first-mover).

These lock in the conversion of Transport Request from a hand-rolled status
machine to the native **Transport Request Workflow**, and in particular prove
the bug being fixed: a **post-submit transition is now reachable**
(Approved -> Scheduled -> Fulfilled), which the old engine left frozen.

Coverage (adversarial / cross-role, not only the happy path):
  * a legal transition by the right role passes (Fleet Supervisor validates;
    a different Fleet Manager authorizes);
  * a wrong role is blocked (no such transition is offered);
  * Segregation of Duties — the requester cannot authorize their own request
    (transition condition ``requested_by != session.user``);
  * Delegation of Authority — an under-tier approver is blocked when the
    server-derived ``needs_operations`` flag is set (only the Operations-tier
    transition remains);
  * the cross-document drives: Route Plan submit -> TR Scheduled, and Dispatch
    Trip completion -> TR Fulfilled;
  * post-submit reachability: Approved -> Scheduled -> Fulfilled is reachable.

The tests drive the real ``frappe.model.workflow.apply_workflow`` as concrete
users, so they exercise the same path a desk action takes (role gate +
condition + docstatus transition), not a mocked shortcut.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex.tests._helpers import _user

WORKFLOW = "Transport Request Workflow"


def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}


class TestTransportRequestWorkflow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A-077: mandatory Salis workflow (salis_workflow_seed, every install/migrate);
        # absence is a regression - FAIL, never skip.
        if get_workflow_name("Transport Request") != WORKFLOW:
            raise AssertionError(
                f"Mandatory Salis workflow {WORKFLOW!r} not active for "
                "'Transport Request' (salis_workflow_seed regression)"
            )
        frappe.set_user("Administrator")
        # [#al91x0]
        cls.requester = _user("tr_req@example.com", "Fleet Project Manager")
        cls.supervisor = _user("tr_sup@example.com", "Fleet Supervisor")
        cls.manager = _user("tr_mgr@example.com", "Fleet Manager")
        cls.project = cls._project("TR Workflow Project")
        # [#l27h20]
        for u in (cls.requester, cls.supervisor):
            if not frappe.db.exists(
                "User Permission",
                {"user": u, "allow": "Project", "for_value": cls.project},
            ):
                frappe.get_doc({
                    "doctype": "User Permission",
                    "user": u,
                    "allow": "Project",
                    "for_value": cls.project,
                }).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        # [#5aa0v7]
        frappe.set_user("Administrator")
        for u in (cls.requester, cls.supervisor):
            frappe.db.delete("User Permission",
                             {"user": u, "allow": "Project", "for_value": cls.project})
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    @staticmethod
    def _project(name):
        p = frappe.db.get_value("Project", {"project_name": name}, "name")
        if not p:
            p = frappe.get_doc(
                {"doctype": "Project", "project_name": name}
            ).insert(ignore_permissions=True).name
        return p

    def _new_tr(self, **overrides):
        """A draft, validatable Administrative Trip (small scope => Regional tier)
        unless overridden. Created as Administrator so ``owner`` is Administrator
        and the SoD gate is exercised purely via ``requested_by``."""
        data = {
            "doctype": "Transport Request",
            "service_line": "Administrative Trip",
            "request_type": "Administrative Trip / Document Signing",
            "destination": "Ministry Office",
            "from_location": "HQ",
            "to_location": "Ministry Office",
            "project": self.project,
            "requested_by": self.requester,
            "source_channel": "Desk",
            "status": "New",
        }
        data.update(overrides)
        return frappe.get_doc(data).insert(ignore_permissions=True)

    def _big_worker_tr(self):
        """An Inter-City Relocation whose worker count exceeds the Operations
        threshold (default 20) so the server sets needs_operations=1."""
        # [#s7h8pv]
        workers = [{"pickup_point": f"P{i}"} for i in range(25)]
        tr = frappe.get_doc({
            "doctype": "Transport Request",
            "service_line": "Inter-City Relocation",
            "request_type": "Inter-City Relocation",
            "from_location": "Camp A",
            "to_location": "Camp B",
            "project": self.project,
            "requested_by": self.requester,
            "source_channel": "Desk",
            "status": "New",
            "workers": workers,
        }).insert(ignore_permissions=True)
        return tr

    # [#3jamj8]

    def test_needs_operations_is_server_derived(self):
        small = self._new_tr()
        self.assertEqual(small.needs_operations, 0)
        big = self._big_worker_tr()
        self.assertEqual(big.worker_count, 25)
        self.assertEqual(big.needs_operations, 1)

    # [#6regdy]

    def test_legal_validate_then_authorize_passes(self):
        tr = self._new_tr()

        frappe.set_user(self.supervisor)
        self.assertIn("Validate", _actions(tr))
        apply_workflow(tr, "Validate")
        tr.reload()
        self.assertEqual(tr.status, "Validated")
        self.assertEqual(tr.docstatus, 0)

        # [#8akzu2]
        frappe.set_user(self.manager)
        self.assertIn("Authorize (Operations)", _actions(tr))
        apply_workflow(tr, "Authorize (Operations)")
        tr.reload()
        self.assertEqual(tr.status, "Approved")
        self.assertEqual(tr.docstatus, 1)

    # [#rwqrmp]

    def test_wrong_role_cannot_authorize(self):
        tr = self._new_tr()
        frappe.set_user(self.supervisor)
        apply_workflow(tr, "Validate")
        tr.reload()

        # [#mlauh0]
        frappe.set_user(self.requester)
        offered = _actions(tr)
        self.assertNotIn("Authorize (Operations)", offered)
        self.assertNotIn("Authorize (Regional)", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(tr, "Authorize (Operations)")

    # [#9rurkc]

    def test_sod_requester_cannot_authorize(self):
        # [#d308xy]
        approver_requester = _user("tr_selfapprove@example.com", "Fleet Manager")
        tr = self._new_tr(requested_by=approver_requester)

        frappe.set_user(self.supervisor)
        apply_workflow(tr, "Validate")
        tr.reload()

        frappe.set_user(approver_requester)
        # [#3f3x5i]
        self.assertNotIn("Authorize (Operations)", _actions(tr))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(tr, "Authorize (Operations)")

        # [#jy5rz2]
        frappe.set_user(self.manager)
        self.assertIn("Authorize (Operations)", _actions(tr))

    # [#tkit1f]

    def test_doa_under_tier_supervisor_blocked_on_ops_request(self):
        tr = self._big_worker_tr()
        self.assertEqual(tr.needs_operations, 1)

        frappe.set_user(self.supervisor)
        apply_workflow(tr, "Validate")
        tr.reload()

        # [#76g0nm]
        frappe.set_user(self.supervisor)
        offered = _actions(tr)
        self.assertNotIn("Authorize (Regional)", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(tr, "Authorize (Regional)")

        # [#svozff]
        frappe.set_user(self.manager)
        self.assertIn("Authorize (Operations)", _actions(tr))
        apply_workflow(tr, "Authorize (Operations)")
        tr.reload()
        self.assertEqual(tr.status, "Approved")

    def test_regional_path_available_for_small_request(self):
        # [#8oibo0]
        tr = self._new_tr()
        frappe.set_user(self.supervisor)
        apply_workflow(tr, "Validate")
        tr.reload()
        frappe.set_user(self.supervisor)
        # [#2ciymj]
        self.assertIn("Authorize (Regional)", _actions(tr))

    # [#4l0dab]

    def test_post_submit_transitions_reachable_via_workflow(self):
        tr = self._new_tr()
        frappe.set_user(self.supervisor)
        apply_workflow(tr, "Validate")
        tr.reload()
        frappe.set_user(self.manager)
        apply_workflow(tr, "Authorize (Operations)")
        tr.reload()
        self.assertEqual(tr.status, "Approved")
        self.assertEqual(tr.docstatus, 1)

        # [#8gmmh9]
        frappe.set_user(self.supervisor)
        self.assertIn("Schedule", _actions(tr))
        apply_workflow(tr, "Schedule")
        tr.reload()
        self.assertEqual(tr.status, "Scheduled")
        self.assertEqual(tr.docstatus, 1)

        self.assertIn("Confirm Fulfilment", _actions(tr))
        apply_workflow(tr, "Confirm Fulfilment")
        tr.reload()
        self.assertEqual(tr.status, "Fulfilled")
        self.assertEqual(tr.docstatus, 1)

    # [#q4vbsq]

    def _approved_tr(self):
        tr = self._new_tr()
        frappe.set_user(self.supervisor)
        apply_workflow(tr, "Validate")
        tr.reload()
        frappe.set_user(self.manager)
        apply_workflow(tr, "Authorize (Operations)")
        frappe.set_user("Administrator")
        tr.reload()
        return tr

    def test_route_plan_submit_drives_request_to_scheduled(self):
        tr = self._approved_tr()
        self.assertEqual(tr.status, "Approved")

        rp = frappe.get_doc({
            "doctype": "Route Plan",
            "route_name": "WF Route 1",
            "transport_request": tr.name,
            "project": self.project,
        }).insert(ignore_permissions=True)
        rp.submit()

        tr.reload()
        self.assertEqual(tr.status, "Scheduled")
        self.assertEqual(tr.route_plan, rp.name)

    def test_dispatch_trip_complete_drives_request_to_fulfilled(self):
        tr = self._approved_tr()

        rp = frappe.get_doc({
            "doctype": "Route Plan",
            "route_name": "WF Route 2",
            "transport_request": tr.name,
            "project": self.project,
        }).insert(ignore_permissions=True)
        rp.submit()
        tr.reload()
        self.assertEqual(tr.status, "Scheduled")

        vehicle = self._vehicle("WF-TRIP-1")
        driver = self._driver("WF Driver 1")
        dt = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "route_plan": rp.name,
            "vehicle": vehicle,
            "driver": driver,
            "trip_date": frappe.utils.today(),
            "status": "Planned",
        }).insert(ignore_permissions=True)

        # [#tpap6c]
        apply_workflow(dt, "Dispatch")
        dt.reload()
        self.assertEqual(dt.status, "Dispatched")
        dt.completion_notes = "Delivered."
        dt.odometer_start = 100
        dt.odometer_end = 180
        dt.save(ignore_permissions=True)
        apply_workflow(dt, "Complete")
        dt.reload()
        self.assertEqual(dt.status, "Completed")
        self.assertEqual(dt.docstatus, 1)

        tr.reload()
        self.assertEqual(tr.status, "Fulfilled")
        self.assertEqual(tr.dispatch_trip, dt.name)
        self.assertEqual(tr.assigned_vehicle, vehicle)

        # [#t0b655]
        apply_workflow(dt, "Cancel")
        dt.reload()
        self.assertEqual(dt.status, "Cancelled")
        self.assertEqual(dt.docstatus, 2)
        tr.reload()
        self.assertEqual(tr.status, "Scheduled")
        self.assertIsNone(tr.dispatch_trip)

    @staticmethod
    def _vehicle(plate):
        v = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
        if not v:
            v = frappe.get_doc({
                "doctype": "Salis Vehicle", "plate_number": plate, "status": "Active",
            }).insert(ignore_permissions=True).name
        return v

    @staticmethod
    def _driver(name):
        d = frappe.db.get_value("Salis Driver", {"full_name": name}, "name")
        if not d:
            d = frappe.get_doc({
                "doctype": "Salis Driver", "full_name": name,
            }).insert(ignore_permissions=True).name
        return d

    # [#4u99m3]

    def test_web_form_draft_insert_starts_at_initial_state(self):
        from apex.salis.web_form.transport_request.transport_request import (
            submit_transport_request,
        )

        frappe.set_user("Guest")
        try:
            result = submit_transport_request(
                from_location="Gate 3",
                to_location="Clinic",
                pickup_datetime=frappe.utils.now_datetime(),
                passenger_count=2,
                purpose="Medical visit",
            )
        finally:
            frappe.set_user("Administrator")

        self.assertTrue(result.get("name"))
        tr = frappe.get_doc("Transport Request", result["name"])
        self.assertEqual(tr.status, "New")
        self.assertEqual(tr.docstatus, 0)
        self.assertEqual(tr.source_channel, "Web QR")
        self.assertTrue(tr.anonymous_tracking_code)
