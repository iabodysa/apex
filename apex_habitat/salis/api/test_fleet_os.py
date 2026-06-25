"""Tests for the Fleet OS dashboard reader's typed empty reason.

get_fleet_os tells an empty board apart from an access gap: ``scope_empty`` (the
user is scoped to no project), ``data_empty`` (the permitted fleet is empty), or
``reason: None`` when vehicles are returned. The project-scope resolver is
patched so each branch is exercised deterministically on a fresh site.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import fleet_os

# get_fleet_os resolves scope through the shared fleet_reader service, so the
# project-scope resolver is patched there (its single home).
_RESOLVER = "apex_habitat.salis.api.fleet_reader._permitted_projects"


class TestFleetOSEmptyReason(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_scope_empty_when_no_permitted_project(self):
        # Scoped user granted no project -> access gap, not an empty fleet.
        with patch(_RESOLVER, return_value=(False, [])):
            r = fleet_os.get_fleet_os()
        self.assertEqual(r["vehicles"], [])
        self.assertEqual(r["reason"], "scope_empty")

    def test_data_empty_when_scope_has_no_vehicles(self):
        # Scoped to a project that owns no vehicle -> genuinely empty board.
        ghost = f"NO-SUCH-PROJECT-{frappe.generate_hash(length=10)}"
        with patch(_RESOLVER, return_value=(False, [ghost])):
            r = fleet_os.get_fleet_os()
        self.assertEqual(r["vehicles"], [])
        self.assertEqual(r["reason"], "data_empty")

    def test_no_reason_when_vehicles_returned(self):
        plate = f"FOS {frappe.generate_hash(length=6)}"
        name = frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
        ).insert(ignore_permissions=True).name
        # Unscoped view sees the whole (non-empty) fleet -> no typed reason.
        with patch(_RESOLVER, return_value=(True, None)):
            r = fleet_os.get_fleet_os()
        self.assertIsNone(r["reason"])
        self.assertTrue(r["vehicles"])
        self.assertIn(plate, [v["plate"] for v in r["vehicles"]], name)


class TestWorkshopEvents(FrappeTestCase):
    """workshop_in/out are audited submittable events, not bare status flips."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.plate = f"WS {frappe.generate_hash(length=6)}"
        self.vehicle = (
            frappe.get_doc(
                {"doctype": "Salis Vehicle", "plate_number": self.plate, "status": "Active"}
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _open_maintenance_stop(self):
        return frappe.db.get_value(
            "Vehicle Stop",
            {"vehicle": self.vehicle, "stop_reason": "Maintenance", "docstatus": 1,
             "return_date": ["is", "not set"]},
            ["name", "stop_reason", "docstatus"],
            as_dict=True,
        )

    def test_workshop_in_creates_submitted_maintenance_stop(self):
        res = fleet_os.workshop_in(self.plate, expected_return="2026-07-01", notes="brakes")
        stop = self._open_maintenance_stop()
        # A submittable record with a reason exists (not a bare status flip).
        self.assertIsNotNone(stop)
        self.assertEqual(stop.name, res["stop"])
        self.assertEqual(stop.stop_reason, "Maintenance")
        self.assertEqual(stop.docstatus, 1)
        # Vehicle reads the workshop state (the board's workshop lane).
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", self.vehicle, "status"), "Under Maintenance"
        )
        # Expected-return + note are captured in the audit notes, not return_date
        # (an empty return_date is the "still in the workshop" invariant).
        notes = frappe.db.get_value("Vehicle Stop", stop.name, "notes") or ""
        self.assertIn("2026-07-01", notes)
        self.assertIn("brakes", notes)
        self.assertFalse(frappe.db.get_value("Vehicle Stop", stop.name, "return_date"))

    def test_workshop_out_closes_stop_and_restores_status(self):
        fleet_os.workshop_in(self.plate)
        stop_name = self._open_maintenance_stop().name
        fleet_os.workshop_out(self.plate)
        # The stop is cancelled and stamped with the workshop-exit date.
        self.assertEqual(frappe.db.get_value("Vehicle Stop", stop_name, "docstatus"), 2)
        self.assertTrue(frappe.db.get_value("Vehicle Stop", stop_name, "return_date"))
        # Vehicle is restored to its pre-workshop status.
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", self.vehicle, "status"), "Active"
        )
        # No open workshop stop remains.
        self.assertIsNone(self._open_maintenance_stop())

    def test_workshop_out_without_open_stop_throws(self):
        # Falsify: with no open workshop stop the return must raise, not no-op.
        with self.assertRaises(frappe.ValidationError):
            fleet_os.workshop_out(self.plate)
