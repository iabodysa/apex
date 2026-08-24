# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.tests.factories import make_building, make_room

test_ignore = ["Maintenance Request"]


def _report(building, **overrides):
    fields = {
        "doctype": "Safety Inspection Report",
        "building": building,
        "inspection_date": today(),
        "inspector": "Administrator",
        "safety_section_clear": 1,
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestSafetyInspectionReportSubmit(FrappeTestCase):
    def test_a_clear_safety_section_generates_no_maintenance_requests(self):
        building = make_building("_T-SIReport Clear")
        room = make_room(building.name, room_number=f"{building.name}-R01")
        doc = _report(
            building.name,
            safety_section_clear=1,
            safety_findings=[
                {
                    "description": "Loose railing",
                    "issue_type": "Structural",
                    "room": room.name,
                }
            ],
        ).insert(ignore_permissions=True)
        doc.submit()
        self.assertEqual(len(doc.get("linked_maintenance_requests") or []), 0)

    def test_an_actionable_finding_generates_a_linked_maintenance_request(self):
        building = make_building("_T-SIReport Actionable")
        room = make_room(building.name, room_number=f"{building.name}-R01")
        doc = _report(
            building.name,
            safety_section_clear=0,
            safety_findings=[
                {
                    "description": "Loose railing",
                    "issue_type": "Structural",
                    "room": room.name,
                }
            ],
        ).insert(ignore_permissions=True)
        doc.submit()
        linked = doc.get("linked_maintenance_requests") or []
        self.assertEqual(len(linked), 1)
        self.assertTrue(frappe.db.exists("Maintenance Request", linked[0].maintenance_request))


class TestSafetyInspectionReportCancel(FrappeTestCase):
    def test_cancelling_unlinks_a_submitted_generated_maintenance_request(self):
        building = make_building("_T-SIReport Cancel")
        room = make_room(building.name, room_number=f"{building.name}-R01")
        doc = _report(
            building.name,
            safety_section_clear=0,
            safety_findings=[
                {
                    "description": "Broken light",
                    "issue_type": "Electrical",
                    "room": room.name,
                }
            ],
        ).insert(ignore_permissions=True)
        doc.submit()
        mr_name = doc.get("linked_maintenance_requests")[0].maintenance_request
        frappe.get_doc("Maintenance Request", mr_name).submit()
        doc.cancel()
        self.assertIsNone(
            frappe.db.get_value("Maintenance Request", mr_name, "source_inspection")
        )
