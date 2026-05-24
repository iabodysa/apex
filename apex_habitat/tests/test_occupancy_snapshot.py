# Copyright (c) 2026, AFMCO and contributors
"""Occupancy Snapshot engine: the daily job writes one read-only point-in-time
row per building (idempotent), and the Occupancy Trend report aggregates them."""

import frappe
from frappe.utils import today
from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.habitat.tasks import daily_occupancy_snapshot
from apex_habitat.habitat.report.occupancy_trend.occupancy_trend import execute


def _h(n=4):
    return frappe.generate_hash(length=n).upper()


class TestOccupancySnapshot(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        self.cost_center = (frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company})
                            or frappe.db.get_value("Cost Center", {"is_group": 0}))
        self.project = frappe.db.get_value("Project", {}) or frappe.get_doc({
            "doctype": "Project", "project_name": "P " + _h(), "company": self.company,
        }).insert(ignore_permissions=True).name
        self.employee = frappe.get_doc({
            "doctype": "Employee", "first_name": "E " + _h(), "company": self.company, "gender": "Male",
            "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01"}).insert(ignore_permissions=True).name
        self.site = frappe.get_doc({"doctype": "Accommodation Site", "site_name": _h(6)}).insert(ignore_permissions=True)
        self.building = frappe.get_doc({
            "doctype": "Accommodation Building", "building_name": "B " + _h(), "site": self.site.name,
            "total_capacity": 4, "default_cost_center": self.cost_center}).insert(ignore_permissions=True)
        self.room = frappe.get_doc({
            "doctype": "Accommodation Room", "naming_series": "ROOM-.####", "building": self.building.name,
            "room_number": "R" + _h(), "bed_capacity": 2}).insert(ignore_permissions=True).name
        self.bed = frappe.get_doc({
            "doctype": "Accommodation Bed", "naming_series": "BED-.####", "room": self.room,
            "bed_code": "B" + _h()}).insert(ignore_permissions=True).name

    def test_snapshot_written_idempotent_and_reported(self):
        a = frappe.get_doc({
            "doctype": "Accommodation Assignment", "employee": self.employee, "project": self.project,
            "cost_center": self.cost_center, "building": self.building.name, "room": self.room,
            "bed": self.bed, "check_in_date": today(), "assignment_type": "New Assignment"})
        a.insert(ignore_permissions=True)
        a.submit()

        daily_occupancy_snapshot()
        snaps = frappe.get_all("Accommodation Occupancy Snapshot",
                               filters={"building": self.building.name, "snapshot_date": today()},
                               fields=["active_occupants", "total_capacity", "occupancy_percent", "available_capacity"])
        self.assertEqual(len(snaps), 1, "expected exactly one snapshot for the building today")
        self.assertEqual(snaps[0].active_occupants, 1)
        self.assertEqual(snaps[0].total_capacity, 4)
        self.assertEqual(snaps[0].occupancy_percent, 25.0)
        self.assertEqual(snaps[0].available_capacity, 3)

        # idempotent: a second run must not duplicate
        daily_occupancy_snapshot()
        self.assertEqual(
            frappe.db.count("Accommodation Occupancy Snapshot",
                            {"building": self.building.name, "snapshot_date": today()}),
            1, "snapshot must be idempotent per building per day")

        # read-only engine: no human create permission
        meta = frappe.get_meta("Accommodation Occupancy Snapshot")
        self.assertFalse(any(p.create for p in meta.permissions), "snapshot must be read-only (no create)")

        # report aggregates the building
        columns, data = execute({"from_date": today(), "to_date": today(), "building": self.building.name})
        mine = [d for d in data if d["building"] == self.building.name]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["avg_occ"], 25.0)
        self.assertEqual(mine[0]["days_over"], 0)
