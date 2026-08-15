# Copyright (c) 2026, AFMCO and contributors
"""State-machine tests: a document may only be created in its initial status
(closing the insert-bypass), and illegal status jumps are rejected.

The Support Ticket state-flow tests were removed when the custom Support Ticket
DocType was retired in favour of the native ERPNext Issue (Issue carries no
initial-status guard and no custom workflow). Dispatch Trip still proves the
controller-level initial-status guard.

These tests focus on the *controller-level* state guards (``_guard_initial_status``,
``_enforce_dispatch_readiness``, ``_require_completion_notes``, odometer validation)
that live in the Dispatch Trip controller independently of the native workflow.
Full workflow-transition and side-effect tests (happy path, cancel reversal, TR
fulfilment, ledger posting) live in the sibling test_dispatch_trip_workflow.py;
the two suites are complementary, not overlapping.

State machine summary (owned by Dispatch Trip Workflow):

    Planned  (docstatus 0)
      |--(Dispatch)--> Dispatched (docstatus 0)
                         |--(Complete)--> Completed  (docstatus 1)
                                            |--(Cancel)--> Cancelled (docstatus 2)

Controller-level guards exercised here:
  * ``_guard_initial_status``      — insert at any state other than Planned is rejected.
  * ``_enforce_dispatch_readiness``— submit without required fields is rejected.
  * ``_require_completion_notes``  — Completed status without notes is rejected.
  * ``_validate_odometer``         — lone start/end or end < start is rejected.
  * Workflow gate (no-op duplicate transition) — applying Dispatch twice raises.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex.tests._helpers import _user
from apex.tests.factories import make_project, purge_doc, purge_trip_request

WORKFLOW = "Dispatch Trip Workflow"


def _h(n=12):
    """Short random hash suffix for unique fixture names."""
    return frappe.generate_hash(length=n).upper()


def _actions(doc):
    """Set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}


class TestDispatchTripStateFlow(FrappeTestCase):
    """Controller-level state-machine tests.

    These tests use the real ``apply_workflow`` path exactly as the desk does, but
    keep fixture setup as thin as possible.  A Route Plan + Transport Request chain
    is required for the ``before_submit`` dispatch-readiness guard, so only the
    lifecycle and readiness tests build that chain.  The initial-status guard and
    odometer/notes guards operate at ``validate`` time and need nothing more than a
    bare Dispatch Trip.

    Cleanup: every fixture is registered with ``addCleanup`` at creation time so it
    is removed even when a test fails mid-way.
    """


    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # mandatory Salis workflow (salis_workflow_seed, every install/
        # migrate); absence is a regression - FAIL, never skip. Resolved lazily here
        # rather than in a class decorator, which would hit frappe.cache at IMPORT.
        if get_workflow_name("Dispatch Trip") != WORKFLOW:
            raise AssertionError(
                f"Mandatory Salis workflow {WORKFLOW!r} not active for "
                "'Dispatch Trip' (salis_workflow_seed regression)"
            )
        frappe.set_user("Administrator")
        cls.manager = _user("ssf_mgr@example.com", "Fleet Manager")
        cls.supervisor = _user("ssf_sup@example.com", "Fleet Supervisor")
        cls.pmanager = _user("ssf_pm@example.com", "Fleet Project Manager")
        cls.project = make_project("SSF Test Project")
        for u in (cls.supervisor, cls.pmanager):
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
        frappe.set_user("Administrator")
        for u in (cls.supervisor, cls.pmanager):
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
    def _make_vehicle(suffix=None, odometer=0):
        plate = "SSF-" + (suffix or _h(12))
        existing = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
        if existing:
            return existing
        return frappe.get_doc({
            "doctype": "Salis Vehicle",
            "plate_number": plate,
            "status": "Active",
            "odometer": odometer,
        }).insert(ignore_permissions=True).name

    @staticmethod
    def _make_driver(suffix=None):
        full_name = "SSF Driver " + (suffix or _h(12))
        existing = frappe.db.get_value("Salis Driver", {"full_name": full_name}, "name")
        if existing:
            return existing
        return frappe.get_doc({
            "doctype": "Salis Driver",
            "full_name": full_name,
            "status": "Active",
        }).insert(ignore_permissions=True).name

    def _make_scheduled_tr(self, project):
        """Build a Transport Request driven all the way to Scheduled, with a
        submitted Route Plan.  Returns ``(tr_doc, route_plan_name)``.
        The caller should register cleanup via ``addCleanup``.

        The plan carries its two stops because a Dispatch Trip copies its executable
        route from the plan (``trip_manifest.copy_route_stops``) and
        ``_enforce_dispatch_readiness`` refuses a trip with no stop to run."""
        tr = frappe.get_doc({
            "doctype": "Transport Request",
            "service_line": "Administrative Trip",
            "request_type": "Administrative Trip / Document Signing",
            "destination": "Ministry Office",
            "from_location": "HQ",
            "to_location": "Ministry Office",
            "project": project,
            "requested_by": self.pmanager,
            "source_channel": "Desk",
            "status": "New",
        }).insert(ignore_permissions=True)

        frappe.set_user(self.supervisor)
        apply_workflow(tr, "Validate")
        tr.reload()
        frappe.set_user(self.manager)
        apply_workflow(tr, "Authorize (Operations)")
        frappe.set_user("Administrator")
        tr.reload()

        rp = frappe.get_doc({
            "doctype": "Route Plan",
            "route_name": "SSF Route " + _h(12),
            "transport_request": tr.name,
            "project": project,
            "stops": [
                {"stop_name": "HQ", "location": "HQ"},
                {"stop_name": "Ministry Office", "location": "Ministry Office"},
            ],
        }).insert(ignore_permissions=True)
        rp.submit()
        tr.reload()
        self.assertEqual(tr.status, "Scheduled")
        return tr, rp.name

    def _make_trip(self, route_plan, vehicle, driver, status="Planned"):
        dt = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "route_plan": route_plan,
            "vehicle": vehicle,
            "driver": driver,
            "trip_date": frappe.utils.today(),
            "status": status,
        }).insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", dt.name))
        return dt



    def test_insert_at_completed_blocked(self):
        """Controller rejects a direct insert at a terminal state (Completed).

        This is the existing guard; it is preserved here as the canonical
        state-flow anchor test so the file always proves the initial-status
        contract regardless of which other tests are skipped."""
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({"doctype": "Dispatch Trip", "status": "Completed"}).insert(
                ignore_permissions=True)

    def test_insert_at_dispatched_blocked(self):
        """Controller rejects a direct insert at Dispatched — only the workflow
        may move a trip to that state."""
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({"doctype": "Dispatch Trip", "status": "Dispatched"}).insert(
                ignore_permissions=True)

    def test_insert_at_cancelled_blocked(self):
        """Controller rejects a direct insert at Cancelled — only the workflow
        may cancel a submitted-Completed trip."""
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({"doctype": "Dispatch Trip", "status": "Cancelled"}).insert(
                ignore_permissions=True)

    def test_insert_at_planned_succeeds(self):
        """The only valid creation state is Planned; the insert must not raise."""
        dt = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "status": "Planned",
            "trip_date": frappe.utils.today(),
        }).insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", dt.name))
        self.assertEqual(dt.status, "Planned")
        self.assertEqual(dt.docstatus, 0)


    def test_happy_path_lifecycle(self):
        """A trip walks Planned → Dispatched → Completed via apply_workflow.

        Verifies status and docstatus at each step, and that completion_notes
        must be set before the Complete transition is applied.  Side-effects
        (TR fulfilment, ledger) are tested in test_dispatch_trip_workflow.py.
        """
        tr, rp = self._make_scheduled_tr(self.project)
        self.addCleanup(lambda: purge_trip_request(tr.name, rp))
        vehicle = self._make_vehicle("HP1")
        driver = self._make_driver("HP1")
        dt = self._make_trip(rp, vehicle, driver)

        self.assertEqual(dt.status, "Planned")
        self.assertEqual(dt.docstatus, 0)

        frappe.set_user(self.supervisor)
        self.assertIn("Dispatch", _actions(dt))
        apply_workflow(dt, "Dispatch")
        dt.reload()
        self.assertEqual(dt.status, "Dispatched")
        self.assertEqual(dt.docstatus, 0)

        frappe.set_user("Administrator")
        dt.completion_notes = "All workers delivered on time."
        dt.odometer_start = 1000
        dt.odometer_end = 1120
        dt.save(ignore_permissions=True)

        frappe.set_user(self.manager)
        self.assertIn("Complete", _actions(dt))
        apply_workflow(dt, "Complete")
        dt.reload()
        self.assertEqual(dt.status, "Completed")
        self.assertEqual(dt.docstatus, 1)


    def test_invalid_transition_from_planned_to_completed_blocked(self):
        """Workflow blocks the Complete action when the trip is still Planned.

        The transition table has no Planned → Completed edge, so apply_workflow
        must raise a ValidationError.
        """
        tr, rp = self._make_scheduled_tr(self.project)
        self.addCleanup(lambda: purge_trip_request(tr.name, rp))
        vehicle = self._make_vehicle("INV1")
        driver = self._make_driver("INV1")
        dt = self._make_trip(rp, vehicle, driver)

        frappe.set_user(self.manager)
        offered = _actions(dt)
        self.assertNotIn("Complete", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(dt, "Complete")


    def test_invalid_transition_from_completed_to_dispatched_blocked(self):
        """Once a trip is Completed (submitted), the only legal next action is
        Cancel (Fleet Manager → Cancelled/docstatus 2).  Dispatch is not
        offered and apply_workflow must raise a ValidationError."""
        tr, rp = self._make_scheduled_tr(self.project)
        self.addCleanup(lambda: purge_trip_request(tr.name, rp))
        vehicle = self._make_vehicle("INV2")
        driver = self._make_driver("INV2")
        dt = self._make_trip(rp, vehicle, driver)

        frappe.set_user(self.manager)
        apply_workflow(dt, "Dispatch")
        dt.reload()
        dt.completion_notes = "Delivered."
        dt.odometer_start = 200
        dt.odometer_end = 240
        frappe.set_user("Administrator")
        dt.save(ignore_permissions=True)
        frappe.set_user(self.manager)
        apply_workflow(dt, "Complete")
        dt.reload()
        self.assertEqual(dt.status, "Completed")

        offered = _actions(dt)
        self.assertNotIn("Dispatch", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(dt, "Dispatch")


    def test_idempotent_transition_dispatch_twice_raises(self):
        """Applying the same Dispatch action twice must raise on the second call.

        After the first Dispatch the trip is in Dispatched state; the Dispatch
        action has no outgoing edge from Dispatched, so the second call must
        raise a ValidationError rather than silently succeeding or crashing."""
        tr, rp = self._make_scheduled_tr(self.project)
        self.addCleanup(lambda: purge_trip_request(tr.name, rp))
        vehicle = self._make_vehicle("IDP1")
        driver = self._make_driver("IDP1")
        dt = self._make_trip(rp, vehicle, driver)

        frappe.set_user(self.manager)
        apply_workflow(dt, "Dispatch")
        dt.reload()
        self.assertEqual(dt.status, "Dispatched")

        dt.reload()
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(dt, "Dispatch")


    def test_submit_without_vehicle_blocked(self):
        """before_submit enforces dispatch readiness: vehicle is required.

        A trip missing the vehicle field must not pass before_submit even when
        the workflow state is otherwise valid.  We bypass the controller validate
        at insert time so the readiness check (before_submit) is the gate under
        test.  The doc is submitted directly as Administrator so no role gate
        interferes; the controller's _enforce_dispatch_readiness must throw."""
        bare = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "status": "Planned",
            "trip_date": frappe.utils.today(),
        })
        bare.flags.ignore_validate = True
        bare.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", bare.name))

        bare.flags.ignore_validate = False
        bare.flags.ignore_mandatory = False

        frappe.db.set_value("Dispatch Trip", bare.name, "status", "Completed")
        bare.reload()
        bare.flags.ignore_validate = False
        bare.flags.ignore_mandatory = False
        with self.assertRaises(frappe.ValidationError):
            bare.submit()


    def test_completion_notes_required_when_status_completed(self):
        """Saving a trip with status=Completed but no completion_notes raises.

        This guard lives in validate(), so it fires on every save, not only on
        submit.  We bypass the workflow to set the status directly so we can
        exercise the controller guard in isolation."""
        bare = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "status": "Planned",
            "trip_date": frappe.utils.today(),
        })
        bare.flags.ignore_validate = True
        bare.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", bare.name))

        bare.status = "Completed"
        bare.completion_notes = ""
        with self.assertRaises(frappe.ValidationError):
            bare.save(ignore_permissions=True)


    def test_odometer_end_less_than_start_blocked(self):
        """Odometer end reading below start reading is rejected at validate.

        The doc is inserted clean (no bypass flags), so the guard runs on the
        first save as well.  Values are then changed on the doc object (without
        a DB round-trip) and a second save must raise."""
        bare = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "status": "Planned",
            "trip_date": frappe.utils.today(),
            "odometer_start": 100,
            "odometer_end": 200,
        }).insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", bare.name))

        bare.odometer_start = 500
        bare.odometer_end = 300
        with self.assertRaises(frappe.ValidationError):
            bare.save(ignore_permissions=True)

    def test_lone_odometer_start_without_end_blocked(self):
        """Setting odometer_start without a matching odometer_end is rejected.

        _validate_odometer treats Int 0 as «not set» (both-or-neither rule).
        A positive start with end=0 has start_set=True, end_set=False and must
        raise a ValidationError."""
        bare = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "status": "Planned",
            "trip_date": frappe.utils.today(),
            "odometer_start": 100,
            "odometer_end": 200,
        }).insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", bare.name))

        bare.odometer_start = 100
        bare.odometer_end = 0
        with self.assertRaises(frappe.ValidationError):
            bare.save(ignore_permissions=True)
