# Copyright (c) 2026, afmcoltd
"""get_arrival_summary — the read-only manager telemetry behind the Arrivals Desk: it counts only
the check-ins of the date and building it was asked about, splits them by labour supplier, counts
the ones placed in an over-capacity bed, and writes nothing.

The building, its room, its ordinary bed, the employees and the supplier all come from
``test_records.json`` — Supplier and Employee from ERPNext's own. The over-capacity bed is still
minted here, because ``is_temporary`` is the flag the count under test reads. The previous form of
this file scoped every case to a building name it never created and passed ``ignore_links=True`` so
Frappe would not notice, which meant the building scope it asserts was never really exercised.

Counts are exact because the second fixture building holds nothing else, and because the arrivals a
case writes are rolled back to a savepoint before the next one runs.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.arrivals_desk import get_arrival_summary

test_dependencies = ["Bed", "Employee", "Supplier"]

BUILDING = "_Test Building 2"
ROOM = "_T-201"
ORDINARY_BED = "_T-201-A"
SUPPLIER = "_Test Supplier"
DATE = "2026-06-20"
OTHER_DATE = "2026-06-19"


class TestArrivalsSummary(FrappeTestCase):
    def setUp(self):
        # FrappeTestCase rolls the database back once per CLASS, not once per method —
        # frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup — so the arrivals
        # one case writes would still be counted by the next, and every count here is exact.
        frappe.db.savepoint("apex_arrivals_summary_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_arrivals_summary_case")

        # Project is deliberately not a test dependency: ERPNext's Project fixture is not
        # idempotent, so the one already on the site is read rather than rebuilt.
        self.project = frappe.db.get_value("Project", {"project_name": "_Test Project"})

        self.over_capacity_bed = frappe.get_doc({
            "doctype": "Bed",
            "naming_series": "BED-.####",
            "room": ROOM,
            "building": BUILDING,
            "bed_code": "_T-201-OC-" + frappe.generate_hash(length=6).upper(),
            "status": "Available",
            "is_temporary": 1,
        }).insert(ignore_permissions=True).name

        self.worker = frappe.get_doc({
            "doctype": "Temporary Worker",
            "worker_name": "_T Worker " + frappe.generate_hash(length=8).upper(),
            "passport_number": "P" + frappe.generate_hash(length=12).upper(),
            "labour_supplier": SUPPLIER,
        }).insert(ignore_permissions=True, ignore_mandatory=True).name

        self._arrival(DATE, "Temporary Worker", self.worker, self.over_capacity_bed)
        self._arrival(DATE, "Employee", self._employee("_Test Employee"), ORDINARY_BED)
        self._arrival(OTHER_DATE, "Employee", self._employee("_Test Employee 1"), ORDINARY_BED)

    def _employee(self, first_name):
        return frappe.db.get_value("Employee", {"first_name": first_name})

    def _arrival(self, check_in_date, party_type, party, bed, building=BUILDING):
        """The docstatus and check-in date are stamped straight onto the row on purpose: the
        endpoint under test reads submitted arrivals, and running the assignment's own submit would
        drag the bed-lock and occupancy gates into a telemetry test that is not about them."""
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "party_type": party_type,
            "party": party,
            "employee": party if party_type == "Employee" else None,
            "project": self.project,
            "building": building,
            "bed": bed,
        })
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        frappe.db.set_value(
            "Housing Assignment", doc.name,
            {"docstatus": 1, "check_in_date": check_in_date}, update_modified=False,
        )
        return doc.name

    def test_the_count_is_scoped_to_the_date_and_the_building_asked_about(self):
        summary = get_arrival_summary(date=DATE, building=BUILDING)

        self.assertEqual(summary["housed_count"], 2, "two arrivals on the date in this building")
        self.assertEqual(summary["date"], DATE)
        self.assertEqual(summary["building"], BUILDING)

    def test_the_supplier_breakdown_separates_the_supplied_worker_from_the_direct_one(self):
        summary = get_arrival_summary(date=DATE, building=BUILDING)
        buckets = {row["supplier"]: row for row in summary["by_supplier"]}

        self.assertIn(SUPPLIER, buckets, "the labour supplier appears as its own bucket")
        self.assertEqual(buckets[SUPPLIER]["count"], 1)
        self.assertEqual(buckets[SUPPLIER]["supplier_name"], SUPPLIER)
        self.assertIn(None, buckets, "the direct (no-supplier) worker is its own bucket")
        self.assertEqual(buckets[None]["count"], 1)

    def test_the_over_capacity_count_reads_the_beds_is_temporary_flag(self):
        summary = get_arrival_summary(date=DATE, building=BUILDING)

        self.assertEqual(summary["over_capacity_count"], 1)

    def test_asking_twice_changes_nothing(self):
        first = get_arrival_summary(date=DATE, building=BUILDING)
        second = get_arrival_summary(date=DATE, building=BUILDING)

        self.assertEqual(first["housed_count"], second["housed_count"])

    def _arrival_in_another_building(self):
        other = "_Test Building"
        bed = frappe.get_doc({
            "doctype": "Bed",
            "naming_series": "BED-.####",
            "room": "_T-101",
            "building": other,
            "bed_code": "_T-101-XB-" + frappe.generate_hash(length=6).upper(),
            "status": "Available",
        }).insert(ignore_permissions=True).name
        self._arrival(DATE, "Employee", self._employee("_Test Employee 2"), bed, building=other)
        return other

    def _scope(self, restrict, allowed):
        """Stub the building scope at the resolver the endpoint calls."""
        from unittest.mock import patch

        from apex.habitat import permissions

        patcher = patch.object(
            permissions, "report_building_scope", return_value=(restrict, allowed)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_omitting_the_building_no_longer_means_the_whole_estate(self):
        """The optional-argument hole: no ``building`` used to mean every building.

        A supervisor scoped to one building asked for "today" and was told the estate's
        housed count, its supplier split, its over-capacity placements and its manifest
        expectation — none of which they may see one document at a time.
        """
        self._arrival_in_another_building()
        self.assertEqual(
            get_arrival_summary(date=DATE)["housed_count"], 3,
            "both buildings' arrivals are on the site, or the next assertion proves nothing",
        )

        self._scope(True, [BUILDING])
        self.assertEqual(
            get_arrival_summary(date=DATE)["housed_count"], 2,
            "the estate-wide summary was not narrowed to the supervisor's building",
        )

    def test_a_supervisor_with_no_building_gets_zeroes_not_the_estate(self):
        self._arrival_in_another_building()
        self._scope(True, [])
        summary = get_arrival_summary(date=DATE)

        self.assertEqual(summary["housed_count"], 0)
        self.assertEqual(summary["by_supplier"], [])
        self.assertEqual(summary["over_capacity_count"], 0)

    def test_an_explicit_building_is_still_answered_on_its_own_merits(self):
        """Scoping must not break the in-scope question it was added to protect."""
        self._scope(True, [BUILDING])
        self.assertEqual(get_arrival_summary(date=DATE, building=BUILDING)["housed_count"], 2)
