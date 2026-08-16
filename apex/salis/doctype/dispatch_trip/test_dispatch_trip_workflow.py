# Copyright (c) 2026, AFMCO and contributors
"""Native Workflow tests for Dispatch Trip (the FINAL status DocType on the
Salis Workflow Spine), plus the controller-level state guards that operate
independently of that workflow.

Two layers are proven here, both against the real ``frappe.model.workflow.apply_workflow``
driven by concrete role-holding users (role gate enforced) — never a mocked shortcut:

  * the WORKFLOW layer — seeded and active for Dispatch Trip, reusing the ``status``
    field, with the docstatus map Planned=0 / Dispatched=0 / Completed=1 / Cancelled=2;
    a trip walks Planned --Dispatch--> Dispatched --Complete--> Completed; ``Complete``
    is the submit transition (docstatus 0 -> 1) and its on_submit side-effects fire
    end-to-end (the linked Transport Request is driven to Fulfilled through *its* own
    native workflow, and the vehicle odometer is advanced); the cancel / call-off path
    (``Cancel``, submitted Completed -> Cancelled, docstatus 1 -> 2) fires the
    ``on_cancel`` reversal; illegal jumps are blocked by the workflow (Planned ->
    Completed skips Dispatched; a draft trip is never offered Cancel);

  * the CONTROLLER layer — ``_guard_initial_status`` (insert at any state other than
    Planned is rejected), ``_enforce_dispatch_readiness`` (submit without required
    fields is rejected), ``_require_completion_notes`` (Completed status without notes
    is rejected), ``_validate_odometer`` (lone start/end or end < start is rejected),
    and the workflow gate refusing a no-op duplicate transition — guards that live in
    the Dispatch Trip controller independently of the native workflow and would still
    have to hold even on a site where the workflow record was never seeded.

Dispatch Trip is project-scoped through its parent Route Plan, so scoped operational
roles are granted a Project User Permission in setUpClass (Fleet Manager is an
unscoped oversight role and needs none). Every fixture is registered with
``addCleanup`` at creation time so it is removed even when a test fails mid-way.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex.tests._helpers import _user
from apex.tests.factories import make_project, make_vehicle, purge_doc, purge_trip_request

WORKFLOW = "Dispatch Trip Workflow"


def _h(n=12):
    """Short random hash suffix for unique fixture names."""
    return frappe.generate_hash(length=n).upper()


def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}


class TestDispatchTripWorkflow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # mandatory Salis workflow (salis_workflow_seed, every install/migrate);
        # absence is a regression - FAIL, never skip.
        if get_workflow_name("Dispatch Trip") != WORKFLOW:
            raise AssertionError(
                f"Mandatory Salis workflow {WORKFLOW!r} not active for "
                "'Dispatch Trip' (salis_workflow_seed regression)"
            )
        frappe.set_user("Administrator")
        cls.supervisor = _user("dtwf_sup@example.com", "Fleet Supervisor")
        cls.pmanager = _user("dtwf_pm@example.com", "Fleet Project Manager")
        cls.manager = _user("dtwf_mgr@example.com", "Fleet Manager")
        cls.project = make_project("DT Workflow Project")
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
    def _driver(name):
        d = frappe.db.get_value("Salis Driver", {"full_name": name}, "name")
        if not d:
            d = frappe.get_doc({
                "doctype": "Salis Driver", "full_name": name, "status": "Active",
            }).insert(ignore_permissions=True).name
        return d

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

    def _scheduled_tr(self):
        """A Transport Request driven (as Administrator) all the way to Scheduled
        with a submitted Route Plan, ready for a Dispatch Trip. Returns
        ``(tr_doc, route_plan_name)``.

        The plan carries its two stops because a Dispatch Trip copies its executable
        route from the plan (``trip_manifest.copy_route_stops``) and dispatch
        readiness refuses a trip with no stop to run."""
        tr = frappe.get_doc({
            "doctype": "Transport Request",
            "service_line": "Administrative Trip",
            "request_type": "Administrative Trip / Document Signing",
            "destination": "Ministry Office",
            "from_location": "HQ",
            "to_location": "Ministry Office",
            "project": self.project,
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
            "route_name": "DT WF Route",
            "transport_request": tr.name,
            "project": self.project,
            "stops": [
                {"stop_name": "HQ", "location": "HQ"},
                {"stop_name": "Ministry Office", "location": "Ministry Office"},
            ],
        }).insert(ignore_permissions=True)
        rp.submit()
        tr.reload()
        self.assertEqual(tr.status, "Scheduled")
        self.addCleanup(lambda: purge_trip_request(tr.name, rp.name))
        return tr, rp.name

    def _make_scheduled_tr(self, project):
        """A Transport Request driven all the way to Scheduled, with a submitted
        Route Plan. Returns ``(tr_doc, route_plan_name)``. The caller registers
        its own cleanup via ``addCleanup`` — unlike ``_scheduled_tr`` above, this
        variant does not clean up after itself.

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

    def _new_trip(self, route_plan, vehicle, driver):
        dt = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "route_plan": route_plan,
            "vehicle": vehicle,
            "driver": driver,
            "trip_date": frappe.utils.today(),
            "status": "Planned",
        }).insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", dt.name))
        return dt

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


    # --- native workflow: seeding, lifecycle, cancel reversal, illegal jumps ----

    def test_workflow_is_seeded_and_active(self):
        self.assertEqual(get_workflow_name("Dispatch Trip"), WORKFLOW)
        self.assertTrue(frappe.db.get_value("Workflow", WORKFLOW, "is_active"))
        self.assertEqual(
            frappe.db.get_value("Workflow", WORKFLOW, "workflow_state_field"), "status"
        )
        states = {
            s.state: s.doc_status
            for s in frappe.get_doc("Workflow", WORKFLOW).states
        }
        self.assertEqual(states["Planned"], "0")
        self.assertEqual(states["Dispatched"], "0")
        self.assertEqual(states["Completed"], "1")
        self.assertEqual(states["Cancelled"], "2")


    def test_walk_to_completed_drives_tr_to_fulfilled_and_updates_odometer(self):
        tr, rp = self._scheduled_tr()
        vehicle = make_vehicle("DT-WF-1", odometer=100)
        driver = self._driver("DT WF Driver 1")
        dt = self._new_trip(rp, vehicle, driver)
        self.assertEqual(dt.docstatus, 0)

        frappe.set_user(self.supervisor)
        self.assertIn("Dispatch", _actions(dt))
        apply_workflow(dt, "Dispatch")
        dt.reload()
        self.assertEqual(dt.status, "Dispatched")
        self.assertEqual(dt.docstatus, 0)

        dt.completion_notes = "Delivered on time."
        dt.odometer_start = 100
        dt.odometer_end = 260
        dt.save(ignore_permissions=True)

        frappe.set_user(self.supervisor)
        self.assertNotIn("Complete", _actions(dt))

        frappe.set_user(self.manager)
        self.assertIn("Complete", _actions(dt))
        apply_workflow(dt, "Complete")
        dt.reload()
        self.assertEqual(dt.status, "Completed")
        self.assertEqual(dt.docstatus, 1)

        tr.reload()
        self.assertEqual(tr.status, "Fulfilled")
        self.assertEqual(tr.dispatch_trip, dt.name)
        self.assertEqual(tr.assigned_vehicle, vehicle)
        self.assertEqual(tr.assigned_driver, driver)

        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", vehicle, "odometer"), 260
        )
        self.assertTrue(
            frappe.db.exists("Trip Fulfilment Ledger", {"dispatch_trip": dt.name})
        )


    def test_cancel_completed_trip_reverses_fulfilment(self):
        tr, rp = self._scheduled_tr()
        vehicle = make_vehicle("DT-WF-2", odometer=500)
        driver = self._driver("DT WF Driver 2")
        dt = self._new_trip(rp, vehicle, driver)

        frappe.set_user(self.manager)
        apply_workflow(dt, "Dispatch")
        dt.reload()
        dt.completion_notes = "Done."
        dt.odometer_start = 500
        dt.odometer_end = 540
        dt.save(ignore_permissions=True)
        apply_workflow(dt, "Complete")
        tr.reload()
        self.assertEqual(tr.status, "Fulfilled")
        self.assertTrue(
            frappe.db.exists("Trip Fulfilment Ledger", {"dispatch_trip": dt.name})
        )

        dt.reload()
        frappe.set_user(self.manager)
        self.assertIn("Cancel", _actions(dt))
        apply_workflow(dt, "Cancel")
        dt.reload()
        self.assertEqual(dt.status, "Cancelled")
        self.assertEqual(dt.docstatus, 2)

        tr.reload()
        self.assertEqual(tr.status, "Scheduled")
        self.assertIsNone(tr.dispatch_trip)
        self.assertIsNone(tr.assigned_vehicle)
        self.assertFalse(
            frappe.db.exists("Trip Fulfilment Ledger", {"dispatch_trip": dt.name})
        )


    def test_illegal_jump_planned_to_completed_blocked(self):
        tr, rp = self._scheduled_tr()
        vehicle = make_vehicle("DT-WF-3", odometer=0)
        driver = self._driver("DT WF Driver 3")
        dt = self._new_trip(rp, vehicle, driver)

        frappe.set_user(self.manager)
        offered = _actions(dt)
        self.assertIn("Dispatch", offered)
        self.assertNotIn("Complete", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(dt, "Complete")

    def test_draft_trip_is_never_offered_cancel(self):
        """A draft (Planned / Dispatched) trip is never offered Cancel — a
        draft -> Cancelled (docstatus 0 -> 2) transition is forbidden by Frappe,
        so it is intentionally absent. A draft trip is called off by deletion."""
        tr, rp = self._scheduled_tr()
        vehicle = make_vehicle("DT-WF-4", odometer=0)
        driver = self._driver("DT WF Driver 4")
        dt = self._new_trip(rp, vehicle, driver)

        frappe.set_user(self.manager)
        self.assertNotIn("Cancel", _actions(dt))
        apply_workflow(dt, "Dispatch")
        dt.reload()
        frappe.set_user(self.manager)
        self.assertNotIn("Cancel", _actions(dt))


    def test_insert_at_completed_blocked(self):
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {"doctype": "Dispatch Trip", "status": "Completed"}
            ).insert(ignore_permissions=True)


    # --- controller-level state guards, independent of the workflow record -----

    def test_state_flow_insert_at_completed_blocked(self):
        """Controller rejects a direct insert at a terminal state (Completed).

        This is the existing guard; it is preserved here as the canonical
        state-flow anchor test so the module always proves the initial-status
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
        must be set before the Complete transition is applied. Side-effects
        (TR fulfilment, ledger) are proved above.
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
        Cancel (Fleet Manager → Cancelled/docstatus 2). Dispatch is not
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
        the workflow state is otherwise valid. We bypass the controller validate
        at insert time so the readiness check (before_submit) is the gate under
        test. The doc is submitted directly as Administrator so no role gate
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
        submit. We bypass the workflow to set the status directly so we can
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
        first save as well. Values are then changed on the doc object (without
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
