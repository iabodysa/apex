# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_building


def _snapshot(**overrides):
    fields = {
        "doctype": "Occupancy Snapshot",
        "snapshot_date": "2026-03-11",
        "building": None,
        "active_occupants": 2,
        "total_capacity": 4,
    }
    fields.update(overrides)
    if fields.get("building") is None:
        fields["building"] = make_building(
            "Occupancy Snapshot Test Building " + frappe.generate_hash(length=6),
            company="_Test Company",
        ).name
    return frappe.get_doc(fields)


class TestOccupancySnapshotIsOnePerBuildingPerDay(FrappeTestCase):
    def test_a_second_snapshot_for_the_same_building_and_date_is_refused(self):
        first = _snapshot().insert(ignore_permissions=True)
        with self.assertRaises(frappe.UniqueValidationError):
            _snapshot(building=first.building, snapshot_date=first.snapshot_date).insert(
                ignore_permissions=True
            )

    def test_the_same_building_on_another_date_is_accepted(self):
        first = _snapshot().insert(ignore_permissions=True)
        second = _snapshot(building=first.building, snapshot_date="2026-03-12").insert(
            ignore_permissions=True
        )
        self.assertNotEqual(first.name, second.name)

    def test_the_same_date_in_another_building_is_accepted(self):
        first = _snapshot().insert(ignore_permissions=True)
        second = _snapshot(snapshot_date=first.snapshot_date).insert(ignore_permissions=True)
        self.assertNotEqual(first.building, second.building)


class TestOccupancySnapshotIdentity(FrappeTestCase):
    def test_framework_refuses_a_snapshot_with_no_date(self):
        with self.assertRaises(frappe.MandatoryError):
            _snapshot(snapshot_date=None).insert(ignore_permissions=True)

    def test_framework_refuses_a_snapshot_with_no_building(self):
        with self.assertRaises(frappe.MandatoryError):
            _snapshot(building="").insert(ignore_permissions=True)

    def test_framework_refuses_a_building_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _snapshot(building="No Such Building " + frappe.generate_hash(length=6)).insert(
                ignore_permissions=True
            )

    def test_the_snapshot_is_named_from_the_declared_series(self):
        doc = _snapshot().insert(ignore_permissions=True)
        self.assertTrue(doc.name.startswith("ACC-OCC-"))
