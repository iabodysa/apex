"""Regression test for the get_fleet_os Damages/Accidents/Stolen panels (T-416).

The /fleet board tabs read ``vehicle.damages`` (Vehicle Damage Write-Off rows),
``vehicle.accidents`` (Accident Vehicle Incident rows) and the card stripe reads
``vehicle.stolen_info`` (the latest Theft incident). ``get_fleet_os`` used to
return all three hardcoded empty, so the tabs always showed the empty state even
for a vehicle that had incidents on record. This guards that they now carry the
real rows in the exact shape the SPA render code reads.

The empty assertion on a second, clean vehicle is non-vacuous: if a future
refactor wrongly fanned every vehicle's incidents onto every card, the clean
vehicle would gain rows and the test would fail.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api.fleet_os import get_fleet_os


class TestFleetOsIncidents(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _vehicle(self, suffix):
        # Salis Vehicle autonames by series, so the SPA "plate" is plate_number,
        # not doc.name — keep both to seed against name and match against plate.
        plate = "FOSINC " + self._testMethodName + suffix
        doc = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": plate,
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        return doc.name, plate

    def _row_for(self, plate):
        for v in get_fleet_os().get("vehicles", []):
            if v.get("plate") == plate:
                return v
        return None

    def test_panels_populate_for_a_vehicle_with_records(self):
        veh_name, veh_plate = self._vehicle("A")
        _clean_name, clean_plate = self._vehicle("B")

        accident = frappe.get_doc(
            {
                "doctype": "Vehicle Incident",
                "incident_type": "Accident",
                "vehicle": veh_name,
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
                "vehicle": veh_name,
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
                "vehicle": veh_name,
                "damage_description": "Bumper beyond repair.",
                "estimated_cost": 2200,
                "evidence": "/files/dummy.pdf",
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        writeoff.submit()

        row = self._row_for(veh_plate)
        self.assertIsNotNone(row, "the seeded vehicle must surface in get_fleet_os")

        # Accidents: the Accident incident, not the Theft.
        self.assertEqual(len(row["accidents"]), 1, "the accident must show on the accidents tab")
        acc = row["accidents"][0]
        self.assertEqual(acc["date"], "2026-06-01")
        self.assertEqual(acc["report_number"], "PR-9001")
        self.assertEqual(acc["estimated_cost"], 1500)
        self.assertTrue(acc["description"])

        # Damages: the write-off, in the SPA's d.{date,cost,description,status} shape.
        self.assertEqual(len(row["damages"]), 1, "the write-off must show on the damages tab")
        dmg = row["damages"][0]
        self.assertEqual(dmg["cost"], 2200)
        self.assertTrue(dmg["date"], "a damage row must carry a date for the card head")
        self.assertTrue(dmg["description"])

        # Stolen: the latest Theft drives stolen_info (the card stripe).
        self.assertIsNotNone(row["stolen_info"], "a theft incident must populate stolen_info")
        self.assertEqual(row["stolen_info"]["date"], "2026-06-10")
        self.assertEqual(row["stolen_info"]["report_number"], "PR-9002")

        # Non-vacuous: a vehicle with no records keeps empty panels.
        clean_row = self._row_for(clean_plate)
        self.assertIsNotNone(clean_row, "the clean vehicle must also surface")
        self.assertEqual(clean_row["accidents"], [])
        self.assertEqual(clean_row["damages"], [])
        self.assertIsNone(clean_row["stolen_info"])
