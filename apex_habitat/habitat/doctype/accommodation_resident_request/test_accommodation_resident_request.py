import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.habitat.doctype.accommodation_resident_request.accommodation_resident_request import (
    advance_triage_status,
    bulk_triage,
)


class TestAccommodationResidentRequest(FrappeTestCase):
    def _request(self, status="New", **kwargs):
        doc = frappe.get_doc({
            "doctype": "Accommodation Resident Request",
            "naming_series": "REQ-.YYYY.-.####",
            "request_category": "Maintenance",
            "description": "Test request",
            "status": status,
            **kwargs,
        })
        doc.insert(ignore_permissions=True)
        return doc

    def test_advance_new_to_triaged(self):
        """One-tap advance moves a New request to Triaged through the save path."""
        doc = self._request("New")
        res = advance_triage_status(doc.name, "Triaged")
        self.assertTrue(res["changed"])
        self.assertEqual(frappe.db.get_value("Accommodation Resident Request", doc.name, "status"), "Triaged")

    def test_advance_rejects_out_of_sequence_jump(self):
        """A jump that skips the guard-free progression is refused — Assigned needs
        an assignee and is never reachable by a one-tap advance."""
        doc = self._request("New")
        with self.assertRaises(frappe.ValidationError):
            advance_triage_status(doc.name, "Assigned")

    def test_advance_is_idempotent(self):
        """Advancing to the current status is a no-op, not an error."""
        doc = self._request("Triaged")
        res = advance_triage_status(doc.name, "Triaged")
        self.assertFalse(res["changed"])

    def test_advance_runs_controller_validation(self):
        """Falsifies that the advance bypasses the rule: New's only allowed target is
        Triaged, so requesting In Progress from New is rejected by the sequence map
        (proving the server, not the client, owns the progression)."""
        doc = self._request("New")
        with self.assertRaises(frappe.ValidationError):
            advance_triage_status(doc.name, "In Progress")

    def test_bulk_triage_only_advances_new_rows(self):
        """Bulk triage advances New rows and leaves non-New rows untouched, applying
        partially rather than failing the whole selection."""
        a = self._request("New")
        b = self._request("New")
        c = self._request("Triaged")
        res = bulk_triage([a.name, b.name, c.name])
        self.assertEqual(res["advanced"], 2)
        self.assertEqual(res["total"], 3)
        self.assertEqual(frappe.db.get_value("Accommodation Resident Request", a.name, "status"), "Triaged")
        self.assertEqual(frappe.db.get_value("Accommodation Resident Request", c.name, "status"), "Triaged")

    def test_bulk_triage_accepts_json_string(self):
        """The whitelisted entry point accepts a JSON-encoded list (how the desk
        client sends an array argument)."""
        a = self._request("New")
        res = bulk_triage(frappe.as_json([a.name]))
        self.assertEqual(res["advanced"], 1)
