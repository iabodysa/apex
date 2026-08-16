# Copyright (c) 2026, AFMCO and contributors
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.resident_request import resident_request as rr
from apex.habitat.doctype.resident_request.resident_request import (
    _apply_priority_rules,
    _bulk_triage_job,
    advance_triage_status,
    bulk_triage,
)
# The MODULE, never the endpoint itself. frappe resolves a request's `cmd` by attribute
# lookup on the module the string names (handler.py:294-303), so importing the function
# here would publish a second dotted path to it -- and the rate-limit window is named
# after the caller's spelling (rate_limiter.py:155), so a second path is a second window.
from apex.habitat.web_form.accommodation_resident_request import (
    accommodation_resident_request as intake,
)


class TestAccommodationResidentRequest(FrappeTestCase):
    def _request(self, status="New", **kwargs):
        doc = frappe.get_doc({
            "doctype": "Resident Request",
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
        self.assertEqual(frappe.db.get_value("Resident Request", doc.name, "status"), "Triaged")

    def test_advance_rejects_any_target_other_than_the_expected_next_status(self):
        """Both cases hit the SAME guard (``if to_status != expected: throw`` —
        resident_request.py:320): Assigned needs an assignee and is never reachable
        by a one-tap advance, and New's only allowed target is Triaged, so In
        Progress is rejected too — proving the server, not the client, owns the
        progression, for more than one disallowed target."""
        doc = self._request("New")
        with self.assertRaises(
            frappe.ValidationError, msg="Assigned is refused: it needs an assignee first"
        ):
            advance_triage_status(doc.name, "Assigned")
        with self.assertRaises(
            frappe.ValidationError, msg="In Progress is refused: New's only allowed target is Triaged"
        ):
            advance_triage_status(doc.name, "In Progress")

    def test_advance_is_idempotent(self):
        """Advancing to the current status is a no-op, not an error."""
        doc = self._request("Triaged")
        res = advance_triage_status(doc.name, "Triaged")
        self.assertFalse(res["changed"])

    def test_bulk_triage_only_advances_new_rows(self):
        """Bulk triage advances New rows and leaves non-New rows untouched, applying
        partially rather than failing the whole selection."""
        a = self._request("New")
        b = self._request("New")
        c = self._request("Triaged")
        res = bulk_triage([a.name, b.name, c.name])
        self.assertEqual(res["advanced"], 2)
        self.assertEqual(res["total"], 3)
        self.assertEqual(frappe.db.get_value("Resident Request", a.name, "status"), "Triaged")
        self.assertEqual(frappe.db.get_value("Resident Request", c.name, "status"), "Triaged")

    def test_bulk_triage_accepts_json_string(self):
        """The whitelisted entry point accepts a JSON-encoded list (how the desk
        client sends an array argument)."""
        a = self._request("New")
        res = bulk_triage(frappe.as_json([a.name]))
        self.assertEqual(res["advanced"], 1)

    def test_bulk_triage_large_selection_is_enqueued(self):
        """A selection larger than the sync limit is handed to a background job so
        the request returns at once (queued, no synchronous count) instead of
        blocking the worker thread on an unbounded client-supplied loop. The job is
        enqueued with the full selection and NOT enqueue_after_commit (there is no
        pending write to piggyback). [[reference-frappe-enqueue-now-and-after-commit]]"""
        names = [f"REQ-FAKE-{i}" for i in range(rr.BULK_TRIAGE_SYNC_LIMIT + 1)]
        with patch.object(rr.frappe, "enqueue") as enq:
            res = bulk_triage(names)
        self.assertTrue(res["queued"])
        self.assertIsNone(res["advanced"])
        self.assertEqual(res["total"], len(names))
        enq.assert_called_once()
        self.assertEqual(
            enq.call_args.args[0],
            "apex.habitat.doctype.resident_request.resident_request._bulk_triage_job",
        )
        self.assertEqual(enq.call_args.kwargs["names"], names)
        self.assertNotEqual(enq.call_args.kwargs.get("enqueue_after_commit"), True)

    def test_bulk_triage_small_selection_stays_inline(self):
        """A within-limit selection is NOT enqueued: it runs inline and returns the
        real advanced count so the desk action shows it immediately."""
        a = self._request("New")
        with patch.object(rr.frappe, "enqueue") as enq:
            res = bulk_triage([a.name])
        enq.assert_not_called()
        self.assertEqual(res["advanced"], 1)
        self.assertNotIn("queued", res)

    def test_bulk_triage_job_advances_like_inline(self):
        """The background job runs the identical per-row triage, so a large-batch
        worker produces the same New -> Triaged result the inline path would, and
        leaves a non-New row untouched (same partial-apply skip rule)."""
        a = self._request("New")
        b = self._request("In Progress")
        _bulk_triage_job([a.name, b.name])
        self.assertEqual(frappe.db.get_value("Resident Request", a.name, "status"), "Triaged")
        self.assertEqual(frappe.db.get_value("Resident Request", b.name, "status"), "In Progress")


    def _active_qr(self):
        """An active QR location whose token resolves to a real building."""
        building = frappe.get_doc({
            "doctype": "Building",
            "building_name": "QR Bldg " + frappe.generate_hash(length=12),
        }).insert(ignore_permissions=True, ignore_links=True)
        qr = frappe.get_doc({
            "doctype": "QR Location",
            "naming_series": "QR-LOC-.####",
            "poster_title": "Test Poster",
            "is_active": 1,
            "building": building.name,
        }).insert(ignore_permissions=True, ignore_links=True)
        return qr.location_token, building.name

    def test_valid_token_resolves_on_update(self):
        """RED before fix: the token resolver ran only in before_insert, so pasting a
        valid active token onto an existing request (building still empty) made the
        validate guard false-throw. GREEN: validate resolves the token too, so the
        save passes and building is populated from the token."""
        token, building = self._active_qr()
        doc = self._request("New")
        self.assertFalse(doc.building)
        doc.location_token = token
        doc.save(ignore_permissions=True)
        self.assertEqual(doc.building, building)

    def test_bad_token_rejected_on_update(self):
        """An unknown/inactive token still fails the guard on update — the resolver
        finds no active QR row, building stays empty, the guard throws."""
        doc = self._request("New")
        doc.location_token = "NOTAREALTOKEN"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)


    def test_priority_substring_does_not_false_bump(self):
        """A description that only contains 'ac' as a substring of an ordinary word
        (contact) must not be bumped to High — the bare-substring match was the bug."""
        doc = frappe._dict(request_category="Other", description="please contact me", priority=None)
        _apply_priority_rules(doc)
        self.assertNotEqual(doc.priority, "High")

    def test_priority_ac_pattern_bumps_on_either_alternative(self):
        """One regex, two alternatives (``_AC_PATTERN = r"\\ba[/\\-]?c\\b|air.?condi"``
        — resident_request.py:182): a whole-word 'ac' request escalates, and so does
        the multi-word 'air conditioning' phrase, proving both branches of the same
        pattern bump priority to High."""
        whole_word = frappe._dict(request_category="AC", description="the ac is broken", priority=None)
        _apply_priority_rules(whole_word)
        self.assertEqual(whole_word.priority, "High", "a whole-word 'ac' term must bump to High")

        phrase = frappe._dict(request_category="Other", description="air conditioning not working", priority=None)
        _apply_priority_rules(phrase)
        self.assertEqual(phrase.priority, "High", "the 'air conditioning' phrase must bump to High")


    def test_honeypot_filled_is_rejected(self):
        """A non-empty honeypot field is treated as spam: the call short-circuits
        with a null result and creates no request row."""
        before = frappe.db.count("Resident Request")
        res = intake.submit_resident_request(
            location_token=None,
            request_type="Maintenance",
            description="spam body",
            website_field="http://spam.example",
        )
        self.assertIsNone(res["name"])
        self.assertEqual(frappe.db.count("Resident Request"), before)

    def test_honeypot_empty_passes(self):
        """An empty honeypot lets a genuine submission through and creates a row
        with a tracking code."""
        res = intake.submit_resident_request(
            location_token=None,
            request_type="Maintenance",
            description="genuine request",
            website_field="",
        )
        self.assertIsNotNone(res["name"])
        self.assertTrue(res["tracking_code"])
        self.assertTrue(frappe.db.exists("Resident Request", res["name"]))

    def test_submission_rolls_back_with_transaction(self):
        """The endpoint no longer issues a manual db.commit(): its insert now
        participates in the enclosing transaction, so a rollback after the call
        (exactly what the framework does on a later exception) undoes the row.
        Under the old commit-in-request code the row would survive the rollback,
        so this asserts the anti-pattern fix. [[reference-frappe-commit-in-request-antipattern]]"""
        frappe.db.savepoint("pre_submit")
        res = intake.submit_resident_request(
            location_token=None,
            request_type="Maintenance",
            description="rollback-safety probe",
            website_field="",
        )
        name = res["name"]
        self.assertTrue(frappe.db.exists("Resident Request", name))
        frappe.db.rollback(save_point="pre_submit")
        self.assertFalse(
            frappe.db.exists("Resident Request", name),
            "the insert must roll back with the transaction; a manual commit would defeat this",
        )
