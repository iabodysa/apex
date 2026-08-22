# Copyright (c) 2026, afmcoltd
"""What a Scheduled Task Instance guarantees, asserted against the DocType itself.

Patterned on frappe's own document lifecycle tests (``frappe/tests/test_document.py``,
``test_update_after_submit``) for the submit/cancel guarantees, and on
``test_naming.py``-style uniqueness tests for the composite index. ``validate``,
``on_submit`` and ``before_cancel`` are module-level functions wired through ``hooks.py``'s
``doc_events``; they only run through the real lifecycle calls exercised below.

Each submitted instance below uses its own ``due_date`` on the same
(assignment, task_catalog) pair — this test class's own rollback only happens once, at
class teardown, so a composite key collision between unrelated test methods would be a
self-inflicted false failure, not a real one.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.scheduled_task_instance.scheduled_task_instance import (
    mark_completed,
    start_task,
)

test_dependencies = ["Scheduled Task Template", "Scheduled Task Assignment", "Safety Task Catalog"]


def _new_assignment_and_catalog():
    assignment = frappe.copy_doc(frappe.get_test_records("Scheduled Task Assignment")[0])
    assignment.insert()
    catalog = frappe.copy_doc(frappe.get_test_records("Safety Task Catalog")[0])
    # task_code carries its own unique constraint and the standing fixture already
    # occupies "_T-SAFE-001", so this copy needs one of its own.
    catalog.task_code = "_T-SAFE-STI-001"
    catalog.insert()
    return assignment.name, catalog.name


def _new_instance(due_date, assignment=None, task_catalog=None):
    instance = frappe.new_doc("Scheduled Task Instance")
    instance.template = "_Test Monthly AC Check"
    instance.due_date = due_date
    if assignment:
        instance.assignment = assignment
    if task_catalog:
        instance.task_catalog = task_catalog
    return instance


class TestScheduledTaskInstance(FrappeTestCase):
    def test_a_missing_due_date_is_refused(self):
        """An instance with no due date is a task nobody is ever alerted to do."""
        instance = frappe.new_doc("Scheduled Task Instance")
        instance.template = "_Test Monthly AC Check"

        with self.assertRaisesRegex(frappe.ValidationError, "Due Date is required"):
            instance.insert()

    def test_a_present_due_date_is_accepted(self):
        """The acceptance counterpart to the refusal above."""
        instance = _new_instance("2026-01-01")
        instance.insert()

        self.assertEqual(instance.due_date, "2026-01-01")

    def test_submitting_an_untouched_instance_defaults_its_status_to_open(self):
        """A submitted instance with no status set yet must still read as Open, or it
        never surfaces on anyone's task list."""
        instance = _new_instance("2026-01-02")
        instance.insert()
        instance.submit()

        self.assertEqual(
            frappe.db.get_value("Scheduled Task Instance", instance.name, "status"), "Open"
        )

    def test_cancelling_without_a_reason_is_refused(self):
        """A Cancellation Reason is the only record of why a scheduled task was withdrawn."""
        instance = _new_instance("2026-01-03")
        instance.insert()
        instance.submit()

        with self.assertRaisesRegex(
            frappe.ValidationError, "Cancellation Reason is required"
        ):
            instance.cancel()

    def test_cancelling_with_a_reason_is_accepted(self):
        """The acceptance counterpart to the refusal above."""
        instance = _new_instance("2026-01-04")
        instance.insert()
        instance.submit()

        instance.cancellation_reason = "_Test task no longer applicable"
        instance.cancel()

        self.assertEqual(
            frappe.db.get_value("Scheduled Task Instance", instance.name, "docstatus"), 2
        )

    def test_posting_the_same_assignment_catalog_and_due_date_twice_is_refused(self):
        """The composite unique index — (assignment, task_catalog, due_date, docstatus)
        — is the backstop against the generator double-inserting the same slot under a
        race; without it the same day's task exists twice."""
        assignment, catalog = _new_assignment_and_catalog()
        first = _new_instance("2026-01-05", assignment=assignment, task_catalog=catalog)
        first.insert()

        duplicate = _new_instance("2026-01-05", assignment=assignment, task_catalog=catalog)
        self.assertRaises(frappe.UniqueValidationError, duplicate.insert)

        self.assertEqual(
            frappe.db.count(
                "Scheduled Task Instance",
                {
                    "assignment": assignment,
                    "task_catalog": catalog,
                    "due_date": "2026-01-05",
                    "docstatus": 0,
                },
            ),
            1,
        )

    def test_start_task_moves_an_open_instance_to_in_progress(self):
        """The one legitimate way an assigned worker signals they have begun."""
        instance = _new_instance("2026-01-06")
        instance.insert()
        instance.submit()

        result = start_task(instance.name)

        self.assertEqual(result["status"], "In Progress")
        self.assertEqual(
            frappe.db.get_value("Scheduled Task Instance", instance.name, "status"),
            "In Progress",
        )

    def test_start_task_refuses_an_instance_that_is_not_open(self):
        """Starting an already-started task would silently re-stamp its comment trail and
        hide that it was ever double-triggered."""
        instance = _new_instance("2026-01-08")
        instance.insert()
        instance.submit()
        start_task(instance.name)

        with self.assertRaisesRegex(frappe.ValidationError, "status Open"):
            start_task(instance.name)

    def test_mark_completed_stamps_a_completed_date_when_none_is_given(self):
        """A worker who marks a task done without filling in a date must still get one —
        the completion record cannot be dateless."""
        instance = _new_instance("2026-01-07")
        instance.insert()
        instance.submit()
        self.assertFalse(instance.completed_date)

        result = mark_completed(instance.name)

        self.assertEqual(result["status"], "Completed")
        self.assertTrue(
            frappe.db.get_value("Scheduled Task Instance", instance.name, "completed_date")
        )

    def test_mark_completed_refuses_an_instance_that_is_already_completed(self):
        """Completing a task twice would be a second completion of the same work."""
        instance = _new_instance("2026-01-09")
        instance.insert()
        instance.submit()
        mark_completed(instance.name)

        with self.assertRaisesRegex(
            frappe.ValidationError, "Open or In Progress Task Instances"
        ):
            mark_completed(instance.name)
