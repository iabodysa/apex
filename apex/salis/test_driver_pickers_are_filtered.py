# Copyright (c) 2026, afmcoltd
"""Every Link field to Salis Driver is graded: it filters the picker, or it is named here.

A picker that offers a stopped driver offers a choice the flow refuses later — a vehicle
assignment, a fuel request and a handover all throw ``rider_block_reason``, and a trip now
refuses the stop itself. The grading and the reason for each unfiltered field live in
``apex/salis/utils/driver_availability.py``; this pins the split so a new field cannot ship
without a verdict.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

PICK_A_WORKING_DRIVER = {
    ("Dispatch Trip", "driver"),
    ("Driver Suspension", "driver"),
    ("Fuel Request", "driver"),
    ("Fuel Quota", "driver"),
    ("Route Assignment", "driver"),
    ("Route Plan", "driver"),
    ("Salis Vehicle", "current_driver"),
    ("Transport Request", "assigned_driver"),
    ("Vehicle Assignment", "driver"),
    ("Vehicle Handover", "to_driver"),
}

PICK_A_WORKING_VEHICLE = {
    ("Dispatch Trip", "vehicle"),
    ("Fuel Quota", "vehicle"),
    ("Fuel Request", "vehicle"),
    ("Route Assignment", "vehicle"),
    ("Route Plan", "vehicle"),
    ("Salis Driver", "current_vehicle"),
    ("Transport Request", "assigned_vehicle"),
    ("Vehicle Assignment", "vehicle"),
    ("Vehicle Handover", "vehicle"),
}


class TestPickersAreFiltered(FrappeTestCase):
    def test_every_driver_link_field_is_either_filtered_or_named_as_historical(self):
        """The population is the point: an ungraded field is the defect, not a wrong filter."""
        self._assert_graded("Salis Driver", PICK_A_WORKING_DRIVER, floor=25)

    def test_every_vehicle_link_field_is_either_filtered_or_named_as_historical(self):
        """Same rule, second master: a released vehicle must not be offered for new work."""
        self._assert_graded("Salis Vehicle", PICK_A_WORKING_VEHICLE, floor=25)

    def _assert_graded(self, master, expected, floor):
        graded, filtered = 0, set()
        for row in frappe.get_all(
            "DocField",
            filters={"fieldtype": "Link", "options": master},
            fields=["parent", "fieldname", "link_filters"],
        ):
            graded += 1
            if row.link_filters:
                filtered.add((row.parent, row.fieldname))
                self.assertEqual(
                    json.loads(row.link_filters),
                    [[master, "status", "=", "Active"]],
                    f"{row.parent}.{row.fieldname} filters on something other than Active; "
                    "a second state rule would disagree with rider_block_reason",
                )
        self.assertGreaterEqual(
            graded, floor, f"the {master} Link enumeration looks empty, not clean"
        )
        self.assertEqual(
            filtered,
            expected,
            f"a Link to {master} either pins the picker to Active or is named in "
            "driver_availability.py with the reason a stopped record belongs there",
        )
