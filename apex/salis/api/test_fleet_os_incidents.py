# Copyright (c) 2026, AFMCO and contributors
"""Regression test for the get_fleet_os Damages/Accidents/Stolen panels.

The /fleet board tabs read ``vehicle.damages`` (Vehicle Damage Write-Off rows),
``vehicle.accidents`` (Accident Vehicle Incident rows) and the card stripe reads
``vehicle.stolen_info`` (the latest Theft incident). ``get_fleet_os`` used to
return all three hardcoded empty, so the tabs always showed the empty state even
for a vehicle that had incidents on record. This guards that they now carry the
real rows in the exact shape the SPA render code reads.

The empty assertion on the second fixture vehicle is non-vacuous: if a future
refactor wrongly fanned every vehicle's incidents onto every card, the clean
vehicle would gain rows and the test would fail.

Both vehicles are the shipped fixtures. The incidents and the write-off ARE the
subject and are still built here; each is cancelled again afterwards so the next
case sees the clean pair the fixture ships.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api.fleet_os import get_fleet_os
from apex.tests._helpers import cancel_submitted_for_cleanup, submit_via_workflow

test_dependencies = ["Salis Vehicle"]

PLATE = "_T ABC 1001"
CLEAN_PLATE = "_T ABC 1002"


def _vehicle(plate):
    return frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")


def _restore(plate):
    """Cancel every record the case hung off the borrowed vehicle and put its status back."""
    name = _vehicle(plate)
    for doctype in ("Vehicle Damage Write-Off", "Vehicle Incident", "Vehicle Suspension"):
        for row in frappe.get_all(doctype, filters={"vehicle": name, "docstatus": 1}, pluck="name"):
            cancel_submitted_for_cleanup(frappe.get_doc(doctype, row))
    frappe.db.set_value("Salis Vehicle", name, {"status": "Active", "current_driver": None})


class TestFleetOsIncidents(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.addCleanup(_restore, PLATE)
        self.addCleanup(frappe.set_user, "Administrator")
        self.vehicle = _vehicle(PLATE)

    def _row_for(self, plate):
        for v in get_fleet_os().get("vehicles", []):
            if v.get("plate") == plate:
                return v
        return None

    def test_panels_populate_for_a_vehicle_with_records(self):
        accident = frappe.get_doc(
            {
                "doctype": "Vehicle Incident",
                "incident_type": "Accident",
                "vehicle": self.vehicle,
                "incident_date": "2026-06-01",
                "location": "Ring Road",
                "report_number": "PR-9001",
                "description": "Rear-ended at a junction.",
                "estimated_cost": 1500,
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        accident.submit()

        theft = frappe.get_doc(
            {
                "doctype": "Vehicle Incident",
                "incident_type": "Theft",
                "vehicle": self.vehicle,
                "incident_date": "2026-06-10",
                "location": "Yard B",
                "report_number": "PR-9002",
                "description": "Reported stolen overnight.",
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        theft.submit()

        writeoff = frappe.get_doc(
            {
                "doctype": "Vehicle Damage Write-Off",
                "vehicle": self.vehicle,
                "damage_description": "Bumper beyond repair.",
                "estimated_cost": 2200,
                "evidence": "/files/dummy.pdf",
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        submit_via_workflow(writeoff)

        row = self._row_for(PLATE)
        self.assertIsNotNone(row, "the fixture vehicle must surface in get_fleet_os")

        self.assertEqual(len(row["accidents"]), 1, "the accident must show on the accidents tab")
        acc = row["accidents"][0]
        self.assertEqual(acc["date"], "2026-06-01")
        self.assertEqual(acc["report_number"], "PR-9001")
        self.assertEqual(acc["estimated_cost"], 1500)
        self.assertTrue(acc["description"])

        self.assertEqual(len(row["damages"]), 1, "the write-off must show on the damages tab")
        dmg = row["damages"][0]
        self.assertEqual(dmg["cost"], 2200)
        self.assertTrue(dmg["date"], "a damage row must carry a date for the card head")
        self.assertTrue(dmg["description"])

        self.assertIsNotNone(row["stolen_info"], "a theft incident must populate stolen_info")
        self.assertEqual(row["stolen_info"]["date"], "2026-06-10")
        self.assertEqual(row["stolen_info"]["report_number"], "PR-9002")

        # Salis Vehicle.status has no "Stolen" option and the Theft controller flips the
        # vehicle to "Stopped", so the board's stolen state can only come from the open
        # incident. Read it off the row: without this the stolen pill counts zero forever,
        # the card stripe never draws and the recover button — gated on this exact value —
        # is unreachable in both the panel and the card grid.
        self.assertEqual(row["vehicle_status"], "stolen")

        clean_row = self._row_for(CLEAN_PLATE)
        self.assertIsNotNone(clean_row, "the second fixture vehicle must also surface")
        self.assertEqual(clean_row["accidents"], [])
        self.assertEqual(clean_row["damages"], [])
        self.assertIsNone(clean_row["stolen_info"])
        self.assertNotEqual(clean_row["vehicle_status"], "stolen")

    def test_a_closed_theft_returns_the_vehicle_to_its_own_status(self):
        theft = frappe.get_doc(
            {
                "doctype": "Vehicle Incident",
                "incident_type": "Theft",
                "vehicle": self.vehicle,
                "incident_date": "2026-06-10",
                "location": "Yard B",
                "report_number": "PR-9003",
                "description": "Recovered the same week.",
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        theft.submit()
        self.assertEqual(self._row_for(PLATE)["vehicle_status"], "stolen")

        theft.db_set("status", "Closed")
        self.assertNotEqual(self._row_for(PLATE)["vehicle_status"], "stolen")
