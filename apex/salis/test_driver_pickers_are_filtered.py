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

ACTIVE_ONLY = ["Salis Driver", "status", "=", "Active"]


class TestDriverPickersAreFiltered(FrappeTestCase):
    def test_every_driver_link_field_is_either_filtered_or_named_as_historical(self):
        """The population is the point: an ungraded field is the defect, not a wrong filter."""
        graded, filtered = 0, set()
        for row in frappe.get_all(
            "DocField",
            filters={"fieldtype": "Link", "options": "Salis Driver"},
            fields=["parent", "fieldname", "link_filters"],
        ):
            graded += 1
            if row.link_filters:
                filtered.add((row.parent, row.fieldname))
                self.assertEqual(
                    json.loads(row.link_filters),
                    [ACTIVE_ONLY],
                    f"{row.parent}.{row.fieldname} filters on something other than Active; "
                    "a second driver-state rule would disagree with rider_block_reason",
                )
        self.assertGreaterEqual(
            graded, 25, "the driver Link enumeration looks empty, not clean"
        )
        self.assertEqual(
            filtered,
            PICK_A_WORKING_DRIVER,
            "a Link to Salis Driver either pins the picker to Active or is named in "
            "driver_availability.py with the reason a stopped driver belongs there",
        )
