# Copyright (c) 2026, afmcoltd
"""Every Link field to a master that carries a state is graded: it filters, or it is named here.

A picker that offers a stopped driver, a released vehicle or a retired template offers a choice
the flow refuses later. The grading and the reason for each unfiltered field live in
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

# A checkbox master carries no judgement: inactive means unpickable, on every field.
IS_ACTIVE_MASTERS = (
    "Safety Task Catalog",
    "Maintenance Material",
    "Scheduled Task Template",
    "Route Template",
    "Custody Asset Category",
    "Work Shift",
    "Vehicle Handover Checklist Template",
)


# A ledger row names the material a cost was already incurred on, and that material may have
# been retired since. Filtering it would hide history from the person reading the ledger.
HISTORICAL = {("Maintenance Cost Ledger", "material")}


class TestSalisDriver(FrappeTestCase):
    def test_every_driver_link_field_is_either_filtered_or_named_as_historical(self):
        """The population is the point: an ungraded field is the defect, not a wrong filter."""
        self._assert_graded("Salis Driver", PICK_A_WORKING_DRIVER, floor=25)

    def test_every_vehicle_link_field_is_either_filtered_or_named_as_historical(self):
        """Same rule, second master: a released vehicle must not be offered for new work."""
        self._assert_graded("Salis Vehicle", PICK_A_WORKING_VEHICLE, floor=25)

    def test_every_is_active_master_offers_only_its_active_records(self):
        offenders, checked = [], 0
        for master in IS_ACTIVE_MASTERS:
            for row in frappe.get_all(
                "DocField",
                filters={"fieldtype": "Link", "options": master},
                fields=["parent", "fieldname", "link_filters"],
            ):
                checked += 1
                if not row.link_filters and (row.parent, row.fieldname) not in HISTORICAL:
                    offenders.append(f"{row.parent}.{row.fieldname}")
        self.assertGreaterEqual(checked, 12, "the is_active enumeration looks empty, not clean")
        self.assertEqual(
            offenders, [], "a picker on an is_active master must not offer a retired record"
        )

    def test_a_bed_offered_for_an_assignment_is_a_free_one(self):
        """The receptionist case: an occupied bed must not be on the list he picks from."""
        for parent, fieldname in (("Housing Assignment", "bed"), ("Room Bed Transfer", "to_bed")):
            stored = frappe.db.get_value(
                "DocField", {"parent": parent, "fieldname": fieldname}, "link_filters"
            )
            self.assertTrue(stored, f"{parent}.{fieldname} offers every bed, occupied included")
            self.assertEqual(json.loads(stored), [["Bed", "status", "=", "Available"]])

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
                    f"{row.parent}.{row.fieldname} filters on something other than Active",
                )
        self.assertGreaterEqual(graded, floor, f"the {master} Link enumeration looks empty")
        self.assertEqual(
            filtered,
            expected,
            f"a Link to {master} either pins the picker to Active or is named in "
            "driver_availability.py with the reason a stopped record belongs there",
        )
