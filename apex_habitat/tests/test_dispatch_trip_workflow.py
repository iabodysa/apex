"""Native Workflow tests for Dispatch Trip (the FINAL status DocType on the
Salis Workflow Spine).

These lock in the conversion of Dispatch Trip from a hand-rolled status machine
(the old ``_ALLOWED_TRANSITIONS`` map + ``_enforce_status_flow``) to the native
**Dispatch Trip Workflow**, and prove the behaviours the workflow now owns plus
the cross-document side-effects the controller still owns:

  * the workflow is seeded and active for Dispatch Trip, reusing the ``status``
    field, with the docstatus map Planned=0 / Dispatched=0 / Completed=1 /
    Cancelled=2;
  * a trip walks Planned --Dispatch--> Dispatched --Complete--> Completed via
    ``apply_workflow`` as concrete role-holding users (role gate enforced);
  * ``Complete`` is the submit transition (docstatus 0 -> 1) and its on_submit
    side-effects fire end-to-end: the linked Transport Request is driven to
    **Fulfilled** through *its* native workflow, and the vehicle odometer is
    advanced;
  * the cancel / call-off path: ``Cancel`` (submitted Completed -> Cancelled,
    docstatus 1 -> 2) fires the ``on_cancel`` reversal — the Transport Request is
    rolled back Fulfilled -> Scheduled and the Trip Fulfilment Ledger row is
    removed;
  * illegal jumps are blocked by the workflow (Planned -> Completed skips
    Dispatched; a draft trip is never offered Cancel — a draft -> Cancelled
    transition is forbidden by Frappe and is intentionally absent);
  * the controller-level initial-status guard still rejects a direct insert at a
    later/terminal status (the insert-bypass the workflow cannot cover).

The tests drive the real ``frappe.model.workflow.apply_workflow`` as concrete
users, exercising the same path a desk action takes (role gate + condition +
docstatus transition), not a mocked shortcut. Dispatch Trip is project-scoped
through its parent Route Plan, so scoped operational roles are granted a Project
User Permission in setUp (Fleet Manager is an unscoped oversight role and needs
none).
"""

import unittest

import frappe
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex_habitat.tests.test_salis_doa import _user

WORKFLOW = "Dispatch Trip Workflow"


def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}


@unittest.skipUnless(
    get_workflow_name("Dispatch Trip") == WORKFLOW,
    "Dispatch Trip Workflow not seeded on this site",
)
class TestDispatchTripWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        # A scoped supervisor + project manager (dispatch operators) and an
        # unscoped Fleet Manager (completes / cancels).
        cls.supervisor = _user("dtwf_sup@example.com", "Fleet Supervisor")
        cls.pmanager = _user("dtwf_pm@example.com", "Fleet Project Manager")
        cls.manager = _user("dtwf_mgr@example.com", "Fleet Manager")
        cls.project = cls._project("DT Workflow Project")
        # Scoped operational roles (Fleet Supervisor / Fleet Project Manager) need
        # a Project User Permission to read/transition project-scoped docs in the
        # chain (Transport Request / Route Plan / Dispatch Trip).
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
        frappe.db.commit()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _project(name):
        p = frappe.db.get_value("Project", {"project_name": name}, "name")
        if not p:
            p = frappe.get_doc(
                {"doctype": "Project", "project_name": name}
            ).insert(ignore_permissions=True).name
        return p

    @staticmethod
    def _vehicle(plate, odometer=0):
        v = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
        if not v:
            v = frappe.get_doc({
                "doctype": "Salis Vehicle",
                "plate_number": plate,
                "status": "Active",
                "odometer": odometer,
            }).insert(ignore_permissions=True).name
        else:
            frappe.db.set_value("Salis Vehicle", v, "odometer", odometer)
        return v

    @staticmethod
    def _driver(name):
        d = frappe.db.get_value("Salis Driver", {"full_name": name}, "name")
        if not d:
            d = frappe.get_doc({
                "doctype": "Salis Driver", "full_name": name, "status": "Active",
            }).insert(ignore_permissions=True).name
        return d

    def _scheduled_tr(self):
        """A Transport Request driven (as Administrator) all the way to Scheduled
        with a submitted Route Plan, ready for a Dispatch Trip. Returns
        ``(tr_doc, route_plan_name)``."""
        tr = frappe.get_doc({
            "doctype": "Transport Request",
            "service_line": "Representatives",
            "request_type": "Administrative Trip / Document Signing",
            "destination": "Ministry Office",
            "from_location": "HQ",
            "to_location": "Ministry Office",
            "project": self.project,
            "requested_by": self.pmanager,
            "source_channel": "Desk",
            "status": "New",
        }).insert(ignore_permissions=True)
        # Drive the TR through its own workflow to Approved.
        frappe.set_user(self.supervisor)
        apply_workflow(tr, "Validate")
        tr.reload()
        frappe.set_user(self.manager)
        apply_workflow(tr, "Authorize (Operations)")
        frappe.set_user("Administrator")
        tr.reload()
        # Submitting a Route Plan drives the TR to Scheduled (cross-doc drive).
        rp = frappe.get_doc({
            "doctype": "Route Plan",
            "route_name": "DT WF Route",
            "transport_request": tr.name,
            "project": self.project,
        }).insert(ignore_permissions=True)
        rp.submit()
        frappe.db.commit()
        tr.reload()
        self.assertEqual(tr.status, "Scheduled")
        self.addCleanup(lambda: self._purge_tr(tr.name, rp.name))
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
        frappe.db.commit()
        self.addCleanup(lambda: self._purge_trip(dt.name))
        return dt

    @staticmethod
    def _purge_trip(name):
        frappe.set_user("Administrator")
        if not frappe.db.exists("Dispatch Trip", name):
            return
        doc = frappe.get_doc("Dispatch Trip", name)
        if doc.docstatus == 1:
            try:
                doc.cancel()
            except Exception:
                pass
        frappe.delete_doc("Dispatch Trip", name, ignore_permissions=True, force=True)
        frappe.db.commit()

    @staticmethod
    def _purge_tr(tr_name, rp_name):
        frappe.set_user("Administrator")
        for ledger in frappe.get_all(
            "Trip Fulfilment Ledger", filters={"transport_request": tr_name}, pluck="name"
        ):
            frappe.delete_doc(
                "Trip Fulfilment Ledger", ledger, ignore_permissions=True, force=True
            )
        if frappe.db.exists("Route Plan", rp_name):
            rp = frappe.get_doc("Route Plan", rp_name)
            if rp.docstatus == 1:
                try:
                    rp.cancel()
                except Exception:
                    pass
            frappe.delete_doc("Route Plan", rp_name, ignore_permissions=True, force=True)
        if frappe.db.exists("Transport Request", tr_name):
            tr = frappe.get_doc("Transport Request", tr_name)
            if tr.docstatus == 1:
                try:
                    tr.cancel()
                except Exception:
                    pass
            frappe.delete_doc(
                "Transport Request", tr_name, ignore_permissions=True, force=True
            )
        frappe.db.commit()

    # ------------------------------------------------------------------ seeded

    def test_workflow_is_seeded_and_active(self):
        self.assertEqual(get_workflow_name("Dispatch Trip"), WORKFLOW)
        self.assertTrue(frappe.db.get_value("Workflow", WORKFLOW, "is_active"))
        self.assertEqual(
            frappe.db.get_value("Workflow", WORKFLOW, "workflow_state_field"), "status"
        )
        # Docstatus map: the submit point is Completed, the cancel is Cancelled.
        states = {
            s.state: s.doc_status
            for s in frappe.get_doc("Workflow", WORKFLOW).states
        }
        self.assertEqual(states["Planned"], "0")
        self.assertEqual(states["Dispatched"], "0")
        self.assertEqual(states["Completed"], "1")
        self.assertEqual(states["Cancelled"], "2")

    # ------------------------------------------------------------------ happy walk + cross-doc

    def test_walk_to_completed_drives_tr_to_fulfilled_and_updates_odometer(self):
        tr, rp = self._scheduled_tr()
        vehicle = self._vehicle("DT-WF-1", odometer=100)
        driver = self._driver("DT WF Driver 1")
        dt = self._new_trip(rp, vehicle, driver)
        self.assertEqual(dt.docstatus, 0)

        # Planned --Dispatch--> Dispatched, by a scoped supervisor (role gate).
        frappe.set_user(self.supervisor)
        self.assertIn("Dispatch", _actions(dt))
        apply_workflow(dt, "Dispatch")
        dt.reload()
        self.assertEqual(dt.status, "Dispatched")
        self.assertEqual(dt.docstatus, 0)

        # Stamp the completion fields while still a draft (writable), then Complete.
        dt.completion_notes = "Delivered on time."
        dt.odometer_start = 100
        dt.odometer_end = 260
        dt.save(ignore_permissions=True)

        # Complete is the submit transition; a Fleet Supervisor lacks submit and is
        # NOT offered it — only Fleet Project Manager / Fleet Manager.
        frappe.set_user(self.supervisor)
        self.assertNotIn("Complete", _actions(dt))

        frappe.set_user(self.manager)
        self.assertIn("Complete", _actions(dt))
        apply_workflow(dt, "Complete")
        dt.reload()
        self.assertEqual(dt.status, "Completed")
        self.assertEqual(dt.docstatus, 1)
        frappe.db.commit()

        # Cross-doc drive: the linked Transport Request reached Fulfilled.
        tr.reload()
        self.assertEqual(tr.status, "Fulfilled")
        self.assertEqual(tr.dispatch_trip, dt.name)
        self.assertEqual(tr.assigned_vehicle, vehicle)
        self.assertEqual(tr.assigned_driver, driver)

        # Side-effect: vehicle odometer advanced to the trip end reading.
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", vehicle, "odometer"), 260
        )
        # The Trip Fulfilment Ledger row was posted.
        self.assertTrue(
            frappe.db.exists("Trip Fulfilment Ledger", {"dispatch_trip": dt.name})
        )

    # ------------------------------------------------------------------ cancel / call-off reversal

    def test_cancel_completed_trip_reverses_fulfilment(self):
        tr, rp = self._scheduled_tr()
        vehicle = self._vehicle("DT-WF-2", odometer=500)
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
        frappe.db.commit()
        tr.reload()
        self.assertEqual(tr.status, "Fulfilled")
        self.assertTrue(
            frappe.db.exists("Trip Fulfilment Ledger", {"dispatch_trip": dt.name})
        )

        # Cancel (submitted Completed -> Cancelled) fires on_cancel reversal.
        dt.reload()
        frappe.set_user(self.manager)
        self.assertIn("Cancel", _actions(dt))
        apply_workflow(dt, "Cancel")
        dt.reload()
        self.assertEqual(dt.status, "Cancelled")
        self.assertEqual(dt.docstatus, 2)
        frappe.db.commit()

        # Reversal: TR rolled back Fulfilled -> Scheduled, link cleared, ledger gone.
        tr.reload()
        self.assertEqual(tr.status, "Scheduled")
        self.assertIsNone(tr.dispatch_trip)
        self.assertIsNone(tr.assigned_vehicle)
        self.assertFalse(
            frappe.db.exists("Trip Fulfilment Ledger", {"dispatch_trip": dt.name})
        )

    # ------------------------------------------------------------------ illegal jumps blocked

    def test_illegal_jump_planned_to_completed_blocked(self):
        tr, rp = self._scheduled_tr()
        vehicle = self._vehicle("DT-WF-3", odometer=0)
        driver = self._driver("DT WF Driver 3")
        dt = self._new_trip(rp, vehicle, driver)

        # From Planned, Complete is not offered (must go through Dispatched first).
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
        vehicle = self._vehicle("DT-WF-4", odometer=0)
        driver = self._driver("DT WF Driver 4")
        dt = self._new_trip(rp, vehicle, driver)

        frappe.set_user(self.manager)
        self.assertNotIn("Cancel", _actions(dt))  # Planned
        apply_workflow(dt, "Dispatch")
        dt.reload()
        frappe.set_user(self.manager)
        self.assertNotIn("Cancel", _actions(dt))  # Dispatched

    # ------------------------------------------------------------------ initial-status guard kept

    def test_insert_at_completed_blocked(self):
        # The initial-status guard stays in the controller (the workflow cannot
        # cover a direct insert at a later/terminal status).
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {"doctype": "Dispatch Trip", "status": "Completed"}
            ).insert(ignore_permissions=True)
