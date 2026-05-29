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

import unittest

import frappe
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex_habitat.tests.test_salis_doa import _user

WORKFLOW = "Transport Request Workflow"


def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}


@unittest.skipUnless(
    get_workflow_name("Transport Request") == WORKFLOW,
    "Transport Request Workflow not seeded on this site",
)
class TestTransportRequestWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        # A requester (Operations-style) and two approvers at different tiers.
        cls.requester = _user("tr_req@example.com", "Fleet Project Manager")
        cls.supervisor = _user("tr_sup@example.com", "Fleet Supervisor")
        cls.manager = _user("tr_mgr@example.com", "Fleet Manager")
        cls.project = cls._project("TR Workflow Project")
        # Scoped roles (Fleet Supervisor / Fleet Project Manager) need a Project
        # User Permission to read/transition project-scoped Transport Requests.
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
        frappe.db.commit()

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
            "service_line": "Representatives",
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
        # worker_count is derived by row count; employee (a Link) is left unset so
        # the test does not depend on seeded Employee master data. Rows carry only
        # a pickup_point.
        workers = [{"pickup_point": f"P{i}"} for i in range(25)]
        tr = frappe.get_doc({
            "doctype": "Transport Request",
            "service_line": "Workers",
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

    # --- server-side DoA derivation (the gate cannot be under-stated) ----------

    def test_needs_operations_is_server_derived(self):
        small = self._new_tr()
        self.assertEqual(small.needs_operations, 0)
        big = self._big_worker_tr()
        self.assertEqual(big.worker_count, 25)
        self.assertEqual(big.needs_operations, 1)

    # --- legal transition by the right role ------------------------------------

    def test_legal_validate_then_authorize_passes(self):
        tr = self._new_tr()

        frappe.set_user(self.supervisor)
        self.assertIn("Validate", _actions(tr))
        apply_workflow(tr, "Validate")
        tr.reload()
        self.assertEqual(tr.status, "Validated")
        self.assertEqual(tr.docstatus, 0)

        # A different Fleet Manager authorizes (Operations tier always allowed).
        frappe.set_user(self.manager)
        self.assertIn("Authorize (Operations)", _actions(tr))
        apply_workflow(tr, "Authorize (Operations)")
        tr.reload()
        self.assertEqual(tr.status, "Approved")
        self.assertEqual(tr.docstatus, 1)

    # --- wrong role is blocked -------------------------------------------------

    def test_wrong_role_cannot_authorize(self):
        tr = self._new_tr()
        frappe.set_user(self.supervisor)
        apply_workflow(tr, "Validate")
        tr.reload()

        # The requester holds only Fleet Project Manager — neither approve
        # transition is offered to that role.
        frappe.set_user(self.requester)
        offered = _actions(tr)
        self.assertNotIn("Authorize (Operations)", offered)
        self.assertNotIn("Authorize (Regional)", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(tr, "Authorize (Operations)")

    # --- Segregation of Duties: requester cannot authorize their own request ---

    def test_sod_requester_cannot_authorize(self):
        # The requester is also a Fleet Manager here, so only the SoD condition
        # (requested_by != session.user) stands between them and self-approval.
        approver_requester = _user("tr_selfapprove@example.com", "Fleet Manager")
        tr = self._new_tr(requested_by=approver_requester)

        frappe.set_user(self.supervisor)
        apply_workflow(tr, "Validate")
        tr.reload()

        frappe.set_user(approver_requester)
        # SoD condition removes the transition for the requester themselves.
        self.assertNotIn("Authorize (Operations)", _actions(tr))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(tr, "Authorize (Operations)")

        # A different Fleet Manager CAN authorize the same request.
        frappe.set_user(self.manager)
        self.assertIn("Authorize (Operations)", _actions(tr))

    # --- Delegation of Authority: under-tier approver blocked ------------------

    def test_doa_under_tier_supervisor_blocked_on_ops_request(self):
        tr = self._big_worker_tr()
        self.assertEqual(tr.needs_operations, 1)

        frappe.set_user(self.supervisor)
        apply_workflow(tr, "Validate")
        tr.reload()

        # needs_operations gates OFF the Regional (Fleet Supervisor) path; the
        # supervisor is left with no authorize action.
        frappe.set_user(self.supervisor)
        offered = _actions(tr)
        self.assertNotIn("Authorize (Regional)", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(tr, "Authorize (Regional)")

        # Only the Operations tier (Fleet Manager) can authorize it.
        frappe.set_user(self.manager)
        self.assertIn("Authorize (Operations)", _actions(tr))
        apply_workflow(tr, "Authorize (Operations)")
        tr.reload()
        self.assertEqual(tr.status, "Approved")

    def test_regional_path_available_for_small_request(self):
        # Mirror: a small request keeps the Regional (Supervisor) path open.
        tr = self._new_tr()
        frappe.set_user(self.supervisor)
        apply_workflow(tr, "Validate")
        tr.reload()
        frappe.set_user(self.supervisor)
        # Supervisor != requester (requester is Fleet Project Manager), so SoD is
        # satisfied and the Regional authorize is offered.
        self.assertIn("Authorize (Regional)", _actions(tr))

    # --- post-submit transition is REACHABLE (the bug being fixed) -------------

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

        # The frozen-post-submit bug: these must now succeed on a docstatus=1 doc.
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

    # --- cross-document drives -------------------------------------------------

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
        frappe.db.commit()

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
        frappe.db.commit()
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
        dt.status = "Dispatched"
        dt.save(ignore_permissions=True)
        dt.status = "Completed"
        dt.completion_notes = "Delivered."
        dt.odometer_start = 100
        dt.odometer_end = 180
        dt.save(ignore_permissions=True)
        dt.submit()
        frappe.db.commit()

        tr.reload()
        self.assertEqual(tr.status, "Fulfilled")
        self.assertEqual(tr.dispatch_trip, dt.name)
        self.assertEqual(tr.assigned_vehicle, vehicle)

        # Cancelling the trip reverts the request to Scheduled (system reversal;
        # workflows are forward-only).
        dt.cancel()
        frappe.db.commit()
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

    # --- the QR / web-form draft-insert path still works -----------------------

    def test_web_form_draft_insert_starts_at_initial_state(self):
        from apex_habitat.salis.web_form.transport_request.transport_request import (
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
