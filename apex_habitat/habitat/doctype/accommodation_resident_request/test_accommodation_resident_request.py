import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.habitat.doctype.accommodation_resident_request.accommodation_resident_request import (
    _apply_priority_rules,
    advance_triage_status,
    bulk_triage,
)
from apex_habitat.habitat.web_form.accommodation_resident_request.accommodation_resident_request import (
    submit_resident_request,
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

    # --- Priority rule word-boundary matching ---

    def test_priority_substring_does_not_false_bump(self):
        """A description that only contains 'ac' as a substring of an ordinary word
        (contact) must not be bumped to High — the bare-substring match was the bug."""
        doc = frappe._dict(request_category="Other", description="please contact me", priority=None)
        _apply_priority_rules(doc)
        self.assertNotEqual(doc.priority, "High")

    def test_priority_genuine_ac_request_bumps(self):
        """A real A/C term as a whole word still escalates to High."""
        doc = frappe._dict(request_category="AC", description="the ac is broken", priority=None)
        _apply_priority_rules(doc)
        self.assertEqual(doc.priority, "High")

    def test_priority_air_conditioning_phrase_bumps(self):
        """The multi-word 'air conditioning' high term also escalates."""
        doc = frappe._dict(request_category="Other", description="air conditioning not working", priority=None)
        _apply_priority_rules(doc)
        self.assertEqual(doc.priority, "High")

    # --- Web Form honeypot ---

    def test_honeypot_filled_is_rejected(self):
        """A non-empty honeypot field is treated as spam: the call short-circuits
        with a null result and creates no request row."""
        before = frappe.db.count("Accommodation Resident Request")
        res = submit_resident_request(
            location_token=None,
            request_type="Maintenance",
            description="spam body",
            website_field="http://spam.example",
        )
        self.assertIsNone(res["name"])
        self.assertEqual(frappe.db.count("Accommodation Resident Request"), before)

    def test_honeypot_empty_passes(self):
        """An empty honeypot lets a genuine submission through and creates a row
        with a tracking code."""
        res = submit_resident_request(
            location_token=None,
            request_type="Maintenance",
            description="genuine request",
            website_field="",
        )
        self.assertIsNotNone(res["name"])
        self.assertTrue(res["tracking_code"])
        self.assertTrue(frappe.db.exists("Accommodation Resident Request", res["name"]))
