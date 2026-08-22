# Copyright (c) 2026, afmcoltd
"""What a Housing Assignment guarantees, asserted against the DocType itself.

This is the template the rest of the suite follows, so its shape matters as much as its
coverage: fixtures come from ``test_records.json`` and ``test_dependencies``, never from a
``setUp`` that builds documents, because a document built in ``setUp`` drifts from the one
the application actually creates and it is rebuilt for every method.

``test_records`` is deliberately NOT defined at module level. ``test_runner.py:396`` takes a
module attribute of that name in preference to the file, and only falls through to
``frappe.get_test_records`` at ``:407`` when none exists — so defining one retires this
DocType's ``test_records.json`` without deleting it.

The subject is the occupancy choke point. Every bed-occupancy transaction in Habitat —
this DocType's submit and cancel, Housing Checkout's, Room Bed Transfer's — funnels through
``recalculate_spatial``, so a test that pins submit and cancel here is testing the path all
three take.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

test_dependencies = ["Building", "Room", "Bed", "Employee", "Project"]


def _a_test_assignment():
    """A fresh copy of the first shipped fixture, read from the file at call time.

    ``frappe.get_test_records`` returns [] for a DocType with no ``test_records.json``
    and raises nothing (frappe/__init__.py:2110-2113), so the index below is what turns
    a missing fixture into a failure instead of a green run over nothing.
    """
    return frappe.copy_doc(frappe.get_test_records("Housing Assignment")[0])


class TestHousingAssignment(FrappeTestCase):
    def test_submitting_an_assignment_raises_the_room_and_building_counts(self):
        """Submit is the only thing that makes an assignment count as occupancy."""
        assignment = _a_test_assignment()
        room_before = frappe.db.get_value("Room", assignment.room, "current_occupancy")
        building_before = frappe.db.get_value(
            "Building", assignment.building, "current_occupants"
        )

        assignment.insert()
        self.assertEqual(
            frappe.db.get_value("Room", assignment.room, "current_occupancy"),
            room_before,
            "a draft assignment must not count as occupancy",
        )

        assignment.submit()
        self.assertEqual(
            frappe.db.get_value("Room", assignment.room, "current_occupancy"),
            room_before + 1,
        )
        self.assertEqual(
            frappe.db.get_value("Building", assignment.building, "current_occupants"),
            building_before + 1,
        )

    def test_cancelling_an_assignment_returns_both_counts(self):
        """Cancel unwinds the same two counters submit moved, or a bed is never freed."""
        assignment = _a_test_assignment()
        assignment.insert()
        assignment.submit()
        room_after_submit = frappe.db.get_value(
            "Room", assignment.room, "current_occupancy"
        )
        building_after_submit = frappe.db.get_value(
            "Building", assignment.building, "current_occupants"
        )

        assignment.cancel()
        self.assertEqual(
            frappe.db.get_value("Room", assignment.room, "current_occupancy"),
            room_after_submit - 1,
        )
        self.assertEqual(
            frappe.db.get_value("Building", assignment.building, "current_occupants"),
            building_after_submit - 1,
        )

    def test_a_temporary_stay_without_an_expected_checkout_is_refused(self):
        """A temporary stay with no end date is an assignment nobody will ever close."""
        assignment = _a_test_assignment()
        assignment.stay_type = "Temporary"
        assignment.expected_checkout_date = None
        with self.assertRaisesRegex(frappe.ValidationError, "required for temporary stays"):
            assignment.insert()

    def test_a_temporary_stay_with_an_expected_checkout_is_accepted(self):
        """The control for the two refusals beside it: neither may be refusing everything.

        A guard proved only in the refusing direction can be a check that always throws.
        """
        assignment = _a_test_assignment()
        assignment.stay_type = "Temporary"
        assignment.check_in_date = today()
        assignment.expected_checkout_date = add_days(today(), 30)
        assignment.insert()
        self.assertTrue(frappe.db.exists("Housing Assignment", assignment.name))

    def test_an_expected_checkout_before_the_checkin_is_refused(self):
        """A stay cannot end before it starts, and the refusal is here rather than in the UI.

        The message is matched, not merely the exception class: with the date field left
        empty this same insert is refused for being empty, and a bare assertRaises would
        pass without the ordering rule ever running.
        """
        assignment = _a_test_assignment()
        assignment.stay_type = "Temporary"
        assignment.check_in_date = today()
        assignment.expected_checkout_date = add_days(today(), -1)
        with self.assertRaisesRegex(frappe.ValidationError, "cannot be earlier than"):
            assignment.insert()

    def test_an_assignment_without_a_project_is_refused(self):
        """Project carries the cost of the stay, so an assignment without one bills nobody."""
        assignment = _a_test_assignment()
        assignment.project = None
        self.assertRaises(frappe.ValidationError, assignment.insert)
