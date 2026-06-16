# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors
# [#hbxspc]

import frappe
from frappe.tests.utils import FrappeTestCase


class TestAccommodationOccupancySnapshot(FrappeTestCase):
    def test_insert_minimal_snapshot(self):
        """Smoke test: a minimal valid snapshot (the mandatory building +
        snapshot_date) inserts, gets a name, and deletes cleanly. Accommodation
        Building only needs a name + capacity, so it is created for real to satisfy
        the mandatory Link."""
        building = frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": "OCC-SMOKE-" + frappe.generate_hash(length=6),
            "total_capacity": 4,
        }).insert(ignore_permissions=True).name

        doc = frappe.get_doc({
            "doctype": "Accommodation Occupancy Snapshot",
            "naming_series": "ACC-OCC-.YYYY.-.#####",
            "snapshot_date": "2026-06-01",
            "building": building,
        })
        doc.insert(ignore_permissions=True)
        self.assertIsNotNone(doc.name)

        frappe.delete_doc("Accommodation Occupancy Snapshot", doc.name, force=True, ignore_permissions=True)
        frappe.delete_doc("Accommodation Building", building, force=True, ignore_permissions=True)
