# Copyright (c) 2026, afmcoltd
"""building_open_requests counts only the resident requests that are still open, and only the ones
raised against the building it was asked about.

Both buildings come from ``test_records.json`` rather than being minted per test method: a
savepoint gives the same delta-free isolation without duplicating the records.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.front_desk import _open_resident_request_statuses, building_open_requests

test_dependencies = ["Building"]

BUILDING = "_Test Building"
OTHER_BUILDING = "_Test Building 2"


class TestBuildingOpenRequests(FrappeTestCase):
    def setUp(self):
        # FrappeTestCase rolls the database back once per CLASS, not once per method —
        # frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup — so requests one
        # case raises would still be counted by the next. A savepoint hands the building back.
        frappe.db.savepoint("apex_building_open_requests_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_building_open_requests_case")

    def _request(self, building, status):
        doc = frappe.get_doc({
            "doctype": "Resident Request",
            "building": building,
            "request_category": "Other",
            "description": "Test request " + frappe.generate_hash(length=12).upper(),
            "status": status,
        })
        if status == "Assigned":
            doc.assigned_to = "Administrator"
        if status in ("Resolved", "Closed"):
            doc.resolution_notes = "Resolved in test"
        doc.insert(ignore_permissions=True)
        return doc.name

    def test_only_the_open_requests_of_the_building_asked_about_are_counted(self):
        self._request(BUILDING, "New")
        self._request(BUILDING, "Triaged")
        self._request(BUILDING, "In Progress")
        self._request(BUILDING, "Resolved")
        self._request(BUILDING, "Closed")
        self._request(OTHER_BUILDING, "New")

        result = building_open_requests(BUILDING)

        self.assertEqual(result["open_requests"], 3, "only the three open requests for this building count")
        self.assertEqual(result["building"], BUILDING)

    def test_a_building_whose_requests_are_all_closed_counts_zero(self):
        self._request(BUILDING, "Closed")

        self.assertEqual(building_open_requests(BUILDING)["open_requests"], 0)

    def test_the_open_statuses_exclude_every_terminal_one(self):
        statuses = _open_resident_request_statuses()

        for terminal in ("Resolved", "Rejected", "Closed"):
            self.assertNotIn(terminal, statuses)
        self.assertIn("New", statuses)
        self.assertEqual(building_open_requests(BUILDING)["statuses"], statuses)
