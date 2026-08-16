# Copyright (c) 2026, afmcoltd
"""Coverage for the assignment-queue reader (``apex.salis.api.assignment_queue``).

Exercises every callable: ``open_queue_rows`` (status filter, per-document grouping
of several assignees, and the vehicle/driver stamping ``_vehicle_driver_refs``
performs per reference type), ``_alert_type_for`` (the display-label branch per
reference type, including the description-sniffed Salis Vehicle case), ``queue_ref``
(resolution and its two failure shapes) and ``queue_events_for_vehicle`` (the one
real scope boundary this module enforces — ONE vehicle, not a project).

A queue row's ``name`` is the anchor ToDo's own name (an id the action endpoints
resolve back to the reference document), never the reference document's name —
rows carry no ``reference_type``/``reference_name`` key at all, only ``vehicle``/
``driver``/``message``. Every assertion below identifies "my" row by the ToDo name
it was built from, or by the ``vehicle``/``driver`` field ``_vehicle_driver_refs``
stamped, matching that shape.

This module performs NO project scoping of its own: its own docstring says "Caller
applies its own scope filtering", and neither ``open_queue_rows`` nor ``queue_ref``
take a project argument to filter by. The caller's project-scope enforcement is
proved against the real caller instead, in
``apex.salis.api.test_operations_alerts.TestOperationsAlerts`` (``get_open_alerts``
project-scope tests), which is where ``_permitted_projects`` actually applies the
filter this module's rows flow through.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import assignment_queue
from apex.tests.factories import fixture_tag, make_vehicle


class TestAssignmentQueue(FrappeTestCase):
    """Fixtures: two fresh vehicles, so a row for one never leaks into a read
    scoped to the other."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        tag = fixture_tag()
        cls.veh_a = make_vehicle(f"AQ-A-{tag}")
        cls.veh_b = make_vehicle(f"AQ-B-{tag}")

    def setUp(self):
        frappe.set_user("Administrator")
        self._created_todos: list[str] = []
        self._created_docs: list[tuple[str, str]] = []

    def tearDown(self):
        frappe.set_user("Administrator")
        for name in self._created_todos:
            if frappe.db.exists("ToDo", name):
                frappe.delete_doc("ToDo", name, ignore_permissions=True, force=True)
        for doctype, name in self._created_docs:
            if frappe.db.exists(doctype, name):
                frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)

    def _todo(self, reference_type, reference_name, status="Open", allocated_to="Administrator", description=None):
        """Insert one queue ToDo (status always a valid Select value at insert
        time) and track it for teardown; returns the document."""
        todo = frappe.get_doc(
            {
                "doctype": "ToDo",
                "reference_type": reference_type,
                "reference_name": reference_name,
                "status": "Open",
                "priority": "Medium",
                "description": description or "assignment_queue coverage fixture",
                "allocated_to": allocated_to,
            }
        ).insert(ignore_permissions=True)
        self._created_todos.append(todo.name)
        if status != "Open":
            frappe.db.set_value("ToDo", todo.name, "status", status)
        return todo

    def _suspension(self, vehicle):
        """A minimal Vehicle Suspension against ``vehicle``, tracked for teardown."""
        doc = frappe.get_doc(
            {
                "doctype": "Vehicle Suspension",
                "vehicle": vehicle,
                "stop_reason": "Maintenance",
                "stop_date": "2026-01-01",
            }
        ).insert(ignore_permissions=True)
        self._created_docs.append(("Vehicle Suspension", doc.name))
        return doc

    def _fuel_quota(self, vehicle, driver=None):
        """A minimal Fuel Quota against ``vehicle``, tracked for teardown."""
        doc = frappe.get_doc(
            {
                "doctype": "Fuel Quota",
                "vehicle": vehicle,
                "driver": driver,
                "period_month": "2026-01",
                "monthly_litres": 100,
            }
        ).insert(ignore_permissions=True)
        self._created_docs.append(("Fuel Quota", doc.name))
        return doc

    def test_open_queue_rows_excludes_closed_status(self):
        """Only Open/Overdue ToDos populate the queue; a Closed one drops out.

        ``status="Overdue"`` is written directly to the column (it is not one of
        ToDo's own Select options — the filter is defensive/forward-compatible),
        mirroring how a background job would mark one overdue without a full
        document re-validate.
        """
        self._todo("Salis Vehicle", self.veh_a, status="Open")
        self._todo("Salis Vehicle", self.veh_b, status="Overdue")
        closed_veh = make_vehicle(f"AQ-C-{fixture_tag()}")
        self._todo("Salis Vehicle", closed_veh, status="Closed")

        vehicles_seen = {r.vehicle for r in assignment_queue.open_queue_rows()}

        self.assertIn(self.veh_a, vehicles_seen)
        self.assertIn(self.veh_b, vehicles_seen)
        self.assertNotIn(closed_veh, vehicles_seen)

    def test_open_queue_rows_groups_several_assignees_into_one_row(self):
        """Two holders on the same document collapse into one row carrying both."""
        self._todo("Salis Vehicle", self.veh_a, allocated_to="Administrator")
        self._todo("Salis Vehicle", self.veh_a, allocated_to="Guest")

        rows = [r for r in assignment_queue.open_queue_rows() if r.vehicle == self.veh_a]

        self.assertEqual(len(rows), 1)
        assignees = frappe.parse_json(rows[0]["_assign"])
        self.assertIn("Administrator", assignees)
        self.assertIn("Guest", assignees)

    def test_open_queue_rows_derives_vehicle_and_driver_by_reference_type(self):
        """``_vehicle_driver_refs`` stamps vehicle/driver correctly for each of the
        reference-type shapes the queue carries, keyed by the anchor ToDo name."""
        suspension = self._suspension(self.veh_a)
        suspension_todo = self._todo("Vehicle Suspension", suspension.name)
        quota = self._fuel_quota(self.veh_b, driver=None)
        quota_todo = self._todo("Fuel Quota", quota.name)
        direct_todo = self._todo("Salis Vehicle", self.veh_a, description="direct vehicle row")

        rows_by_todo = {r.name: r for r in assignment_queue.open_queue_rows()}

        self.assertEqual(rows_by_todo[suspension_todo.name]["vehicle"], self.veh_a)
        self.assertIsNone(rows_by_todo[suspension_todo.name]["driver"])
        self.assertEqual(rows_by_todo[quota_todo.name]["vehicle"], self.veh_b)
        self.assertEqual(rows_by_todo[direct_todo.name]["vehicle"], self.veh_a)
        self.assertIsNone(rows_by_todo[direct_todo.name]["driver"])

    def test_alert_type_for_known_reference_types(self):
        """Each hard-mapped reference type gets its fixed display label."""
        self.assertEqual(
            assignment_queue._alert_type_for("Vehicle Suspension", None), "Maintenance Overdue"
        )
        self.assertEqual(assignment_queue._alert_type_for("Fuel Quota", None), "Excessive Topup")
        self.assertEqual(assignment_queue._alert_type_for("Rental Office", None), "Unsettled Rental")
        self.assertEqual(assignment_queue._alert_type_for("Salis Driver", None), "Supervisor Delay")

    def test_alert_type_for_vehicle_reads_description_for_compliance(self):
        """Salis Vehicle has no fixed label — the description text decides between
        License Expiry (compliance watcher) and Idle Vehicle (idle watcher)."""
        self.assertEqual(
            assignment_queue._alert_type_for("Salis Vehicle", "compliance document expiring"),
            "License Expiry",
        )
        self.assertEqual(
            assignment_queue._alert_type_for("Salis Vehicle", "idle for 9 days"), "Idle Vehicle"
        )

    def test_queue_ref_resolves_a_real_queue_row(self):
        """``queue_ref`` returns the reference behind a live queue ToDo."""
        todo = self._todo("Salis Vehicle", self.veh_a)
        ref = assignment_queue.queue_ref(todo.name)
        self.assertEqual(ref.reference_type, "Salis Vehicle")
        self.assertEqual(ref.reference_name, self.veh_a)

    def test_queue_ref_returns_none_for_non_queue_reference_type(self):
        """A ToDo referencing a DocType outside QUEUE_DOCTYPES is not a queue row,
        even though the ToDo itself is real and open."""
        todo = self._todo("Employee", "_T-Employee-00001")
        self.assertIsNone(assignment_queue.queue_ref(todo.name))

    def test_queue_ref_returns_none_when_row_missing(self):
        """A name that names no ToDo at all resolves to None, not an error."""
        self.assertIsNone(assignment_queue.queue_ref(f"NO-SUCH-TODO-{fixture_tag()}"))

    def test_queue_events_for_vehicle_scoped_to_one_vehicle(self):
        """Events for one vehicle never include another vehicle's queue history —
        the one real scope boundary this module enforces."""
        self._todo("Salis Vehicle", self.veh_a, description="vehicle A event")
        self._todo("Salis Vehicle", self.veh_b, description="vehicle B event")

        events = assignment_queue.queue_events_for_vehicle(self.veh_a, ["Open", "Overdue"], 50)
        refs_seen = {(e.reference_type, e.reference_name) for e in events}

        self.assertIn(("Salis Vehicle", self.veh_a), refs_seen)
        self.assertNotIn(("Salis Vehicle", self.veh_b), refs_seen)

    def test_queue_events_for_vehicle_includes_linked_suspension_and_fuel_quota(self):
        """The vehicle's Vehicle Suspension and Fuel Quota rows are pulled into its
        timeline too, not only its own direct ToDos."""
        suspension = self._suspension(self.veh_a)
        self._todo("Vehicle Suspension", suspension.name)
        quota = self._fuel_quota(self.veh_a)
        self._todo("Fuel Quota", quota.name)

        events = assignment_queue.queue_events_for_vehicle(self.veh_a, ["Open", "Overdue"], 50)
        refs_seen = {(e.reference_type, e.reference_name) for e in events}

        self.assertIn(("Vehicle Suspension", suspension.name), refs_seen)
        self.assertIn(("Fuel Quota", quota.name), refs_seen)

    def test_queue_events_for_vehicle_status_filter_maps_closed_to_resolved(self):
        """A Closed ToDo shows up only when ``Closed`` is requested, and renders
        as the ``Resolved`` status label."""
        todo = self._todo("Salis Vehicle", self.veh_a, status="Closed")

        open_events = assignment_queue.queue_events_for_vehicle(self.veh_a, ["Open", "Overdue"], 50)
        self.assertNotIn(todo.name, {e.name for e in open_events})

        closed_events = assignment_queue.queue_events_for_vehicle(self.veh_a, ["Closed"], 50)
        closed_by_name = {e.name: e for e in closed_events}
        self.assertIn(todo.name, closed_by_name)
        self.assertEqual(closed_by_name[todo.name]["status"], "Resolved")
