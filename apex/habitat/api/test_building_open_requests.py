# Copyright (c) 2026, AFMCO and contributors
"""building_open_requests(building) counts only OPEN (non-terminal) Accommodation
Resident Requests for the given building. Provisions its own building + requests
so it passes on a fresh CI site; asserts are delta-free because each request is
created against a freshly-made building scoped to this test."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.front_desk import (
    _open_resident_request_statuses,
    building_open_requests,
)


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestBuildingOpenRequests(FrappeTestCase):
    def setUp(self):
        self._requests = []
        self.building = self._building()
        self.other_building = self._building()

    def _building(self):
        doc = frappe.get_doc({"doctype": "Building", "building_name": "BLDG-" + _h()})
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.addCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    def _request(self, building, status):
        doc = frappe.get_doc({
            "doctype": "Resident Request",
            "building": building,
            "request_category": "Other",
            "description": "Test request " + _h(),
            "status": status,
        })
        # Satisfy the controller's status-transition validators.
        if status == "Assigned":
            doc.assigned_to = "Administrator"
        if status in ("Resolved", "Closed"):
            doc.resolution_notes = "Resolved in test"
        doc.insert(ignore_permissions=True)
        self._requests.append(doc.name)
        return doc.name

    def tearDown(self):
        for name in self._requests:
            frappe.delete_doc("Resident Request", name, force=True, ignore_permissions=True)

    def test_counts_only_open_requests_for_the_building(self):
        # Three open requests across distinct open statuses.
        self._request(self.building, "New")
        self._request(self.building, "Triaged")
        self._request(self.building, "In Progress")
        # Terminal requests must NOT count.
        self._request(self.building, "Resolved")
        self._request(self.building, "Closed")
        # A different building's open request must NOT leak into the count.
        self._request(self.other_building, "New")

        result = building_open_requests(self.building)
        self.assertEqual(result["open_requests"], 3, "only the 3 open requests for this building count")
        self.assertEqual(result["building"], self.building)

    def test_zero_when_building_has_no_open_requests(self):
        self._request(self.building, "Closed")
        self.assertEqual(building_open_requests(self.building)["open_requests"], 0)

    def test_open_statuses_exclude_terminal_set(self):
        statuses = _open_resident_request_statuses()
        for terminal in ("Resolved", "Rejected", "Closed"):
            self.assertNotIn(terminal, statuses)
        # The returned statuses drive the client filter, so they must be non-empty.
        self.assertIn("New", statuses)
        self.assertEqual(building_open_requests(self.building)["statuses"], statuses)
