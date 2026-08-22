# Copyright (c) 2026, AFMCO and contributors
"""Resident Request behaviour across four concerns that all sit on the one DocType:

* ``TestAccommodationResidentRequest`` — the triage lifecycle (one-tap advance, bulk
  triage sync/async split), QR-token building resolution, priority-rule bumping, the
  public intake endpoint (honeypot + transaction rollback), and the native ToDo
  created/closed by an assignment.
* ``TestResidentRequestConvert`` — converting a triaged request into the operational
  document that does the work (Maintenance Request / Safety Incident), and the
  back-link stamped onto the request for traceability.
* ``TestResidentRequestUsesNativeAssignment`` / ``TestNativeUnassignDoesNotWedgeTheRequest``
  — assignment belongs to Frappe, not to this controller. Two defects are held here:
  ``_assign`` was written by hand as ``[assigned_to]``, which replaced the aggregate
  ``ToDo.on_update`` -> ``update_in_reference`` builds from every live ToDo — a second
  assignee disappeared from the desk badge. Nothing in this module may write ``_assign``.
  And ``status="Assigned"`` refused to save without ``assigned_to``, on a field the
  native unassign clears behind the document. That wedged every later save.
  ``assigned_to`` is read-only so the desk cannot reach that state any other way. Both
  classes patch ``resident_request.frappe`` wholesale and never touch the database, so
  they run as plain ``unittest.TestCase``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.resident_request import resident_request
from apex.habitat.doctype.resident_request import resident_request as rr
from apex.habitat.doctype.resident_request.resident_request import (
    _apply_priority_rules,
    _bulk_triage_job,
    advance_triage_status,
    bulk_triage,
)
from apex.habitat.web_form.accommodation_resident_request import (
    accommodation_resident_request as intake,
)
from apex.tests.factories import ApexHabitatTestCase
from apex.tests import factories
from frappe.model import get_permitted_fields
from apex.tests._helpers import _user, as_user

test_ignore = factories.test_ignore

def _open_todos(name, user="Administrator"):
    return frappe.get_all("ToDo", filters={
        "reference_type": "Resident Request", "reference_name": name,
        "allocated_to": user, "status": "Open"})

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

    def _new_request(self):
        doc = frappe.get_doc({
            "doctype": "Resident Request",
            "request_category": "Maintenance",
            "description": "Test request " + frappe.generate_hash(length=12),
            "status": "New",
        })
        doc.insert(ignore_permissions=True)
        return doc

    def test_assign_creates_todo_then_resolve_closes_it(self):
        """Assigning creates one ToDo, re-saving does not duplicate it, and
        resolving closes it. The ToDo creation is idempotent (no duplicate per
        assignee)."""
        doc = self._new_request()
        self.assertEqual(len(_open_todos(doc.name)), 0)

        doc.status = "Assigned"
        doc.assigned_to = "Administrator"
        doc.save(ignore_permissions=True)
        self.assertEqual(len(_open_todos(doc.name)), 1, "assigning must create one ToDo")

        doc.save(ignore_permissions=True)
        self.assertEqual(len(_open_todos(doc.name)), 1, "no duplicate ToDo on re-save")

        doc.status = "Resolved"
        doc.resolution_notes = "Done"
        doc.save(ignore_permissions=True)
        self.assertEqual(len(_open_todos(doc.name)), 0, "resolving must close the ToDo")

class TestResidentRequestConvert(ApexHabitatTestCase):
    """Converting a triaged Accommodation Resident Request into the operational
    document that does the work, and stamping the back-link (target_doctype /
    target_document) onto the request for traceability. Mirrors the Maintenance
    Request -> Work Order mapper pattern."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        factories.make_company("Test AFMCO")
        cls.building = factories.make_building("RRC-BLDG", company="Test AFMCO")
        cls.room = factories.make_room("RRC-BLDG", room_number="RRC-BLDG-R01")

    def _new_request(self, category="Maintenance", priority="High", **kw):
        doc = frappe.get_doc({
            "doctype": "Resident Request",
            "request_category": category,
            "priority": priority,
            "description": "Convert test " + frappe.generate_hash(length=12),
            "building": "RRC-BLDG",
            "room": "RRC-BLDG-R01",
            "status": "New",
            **kw,
        })
        doc.insert(ignore_permissions=True)
        return doc

    def _convert(self, name):
        from apex.habitat.doctype.resident_request.resident_request import (
            convert_request,
        )
        return convert_request(name)

    def test_maintenance_category_creates_maintenance_request_and_links_back(self):
        req = self._new_request(category="Plumbing", priority="High")
        res = self._convert(req.name)

        self.assertEqual(res["target_doctype"], "Maintenance Request")
        self.assertTrue(res["target_document"])
        self.assertFalse(res["already_converted"])

        req.reload()
        self.assertEqual(req.target_doctype, "Maintenance Request")
        self.assertEqual(req.target_document, res["target_document"])
        self.assertEqual(req.status, "In Progress")

        mr = frappe.get_doc("Maintenance Request", res["target_document"])
        self.assertEqual(mr.building, "RRC-BLDG")
        self.assertEqual(mr.room, "RRC-BLDG-R01")
        self.assertEqual(mr.priority, "High")
        self.assertEqual(mr.issue_type, "Plumbing")
        self.assertEqual(mr.issue_description, req.description)

    def test_conversion_is_idempotent(self):
        req = self._new_request(category="Maintenance")
        first = self._convert(req.name)
        second = self._convert(req.name)

        self.assertFalse(first["already_converted"])
        self.assertTrue(second["already_converted"])
        self.assertEqual(first["target_document"], second["target_document"])

        count = frappe.db.count("Maintenance Request",
                                {"name": first["target_document"]})
        self.assertEqual(count, 1)

    def test_safety_category_creates_safety_incident(self):
        req = self._new_request(category="Safety", priority="Critical",
                                issue_location="Staircase")
        res = self._convert(req.name)

        self.assertEqual(res["target_doctype"], "Safety Incident")
        inc = frappe.get_doc("Safety Incident", res["target_document"])
        self.assertEqual(inc.building, "RRC-BLDG")
        self.assertEqual(inc.severity, "Critical")

        req.reload()
        self.assertEqual(req.target_doctype, "Safety Incident")
        self.assertEqual(req.target_document, res["target_document"])

    def test_non_convertible_category_throws(self):
        req = self._new_request(category="Suggestion")
        with self.assertRaises(frappe.exceptions.ValidationError):
            self._convert(req.name)

        req.reload()
        self.assertFalse(req.target_doctype)
        self.assertFalse(req.target_document)

    def test_terminal_status_is_not_overridden_on_convert(self):
        req = self._new_request(category="Maintenance", status="Resolved",
                                resolution_notes="Closed at source")
        res = self._convert(req.name)
        req.reload()
        self.assertEqual(req.status, "Resolved")
        self.assertEqual(req.target_document, res["target_document"])

def _raising_frappe() -> MagicMock:
    fake = MagicMock()

    def throw(message, exc=None, **_kwargs):
        raise (exc or frappe.ValidationError)(message)

    fake.throw.side_effect = throw
    fake.as_json.side_effect = json.dumps
    return fake

def _mock_request(status, assigned_to=None, priority="Medium"):
    doc = MagicMock(
        doctype="Resident Request",
        status=status,
        assigned_to=assigned_to,
        priority=priority,
    )
    doc.name = "RR-1"
    return doc

class TestResidentRequestUsesNativeAssignment(TestCase):
    def _sync(self, doc):
        fake = _raising_frappe()
        with (
            patch.object(resident_request, "frappe", fake),
            patch.object(resident_request, "_", side_effect=lambda message: message),
            patch.object(resident_request, "add_assignment") as add,
            patch.object(resident_request, "close_all_assignments") as close,
        ):
            resident_request.on_update(doc)
        return fake, add, close

    def test_assignment_goes_through_the_native_api_and_never_writes_assign(self):
        fake, add, close = self._sync(_mock_request("Assigned", "supervisor@example.com"))

        args = add.call_args.args[0]
        self.assertEqual(args["doctype"], "Resident Request")
        self.assertEqual(args["name"], "RR-1")
        self.assertEqual(json.loads(args["assign_to"]), ["supervisor@example.com"])
        close.assert_not_called()
        self.assertNotIn(
            "_assign",
            [call.args[2] for call in fake.db.set_value.call_args_list if len(call.args) > 2],
            "_assign is the ToDo controller's cache; writing it here loses every other assignee",
        )

    def test_a_closing_status_closes_the_native_assignments(self):
        for status in ("Resolved", "Rejected", "Closed"):
            with self.subTest(status=status):
                fake, add, close = self._sync(_mock_request(status, "supervisor@example.com"))
                close.assert_called_once_with("Resident Request", "RR-1")
                add.assert_not_called()
                fake.db.set_value.assert_not_called()

    def test_no_todo_is_inserted_by_hand(self):
        fake, _add, _close = self._sync(_mock_request("Assigned", "supervisor@example.com"))
        self.assertEqual(
            [call for call in fake.get_doc.call_args_list],
            [],
            "the ToDo is inserted by assign_to.add, not by this module",
        )

class TestNativeUnassignDoesNotWedgeTheRequest(TestCase):
    def _validate_status(self, doc):
        fake = _raising_frappe()
        with (
            patch.object(resident_request, "frappe", fake),
            patch.object(resident_request, "_", side_effect=lambda message: message),
        ):
            resident_request._validate_status_transition(doc)

    def test_assigned_without_an_assignee_falls_back_instead_of_refusing(self):
        doc = _mock_request("Assigned", None)
        self._validate_status(doc)
        self.assertEqual(
            doc.status,
            "New",
            "a native unassign must return the request to the queue, not block every save",
        )

    def test_assigned_to_is_read_only_so_only_the_native_assignment_writes_it(self):
        meta = json.loads(
            Path(__file__).with_name("resident_request.json").read_text(encoding="utf-8")
        )
        field = next(f for f in meta["fields"] if f["fieldname"] == "assigned_to")
        self.assertTrue(
            field.get("read_only"),
            "a second writer on assigned_to is what let status and assignment disagree",
        )

DOCTYPE = "Resident Request"
ROLE = "Resident Request Coordinator"
COORDINATOR = "resident_request_coordinator_perms@example.com"
CONFIDENTIAL_FIELD = "mobile_number"
OTHER_OPENERS = ("System Manager", "Accommodation Manager", "Resident Supervisor")
class TestResidentRequestCoordinatorPermissions(FrappeTestCase):
    """What the Resident Request Coordinator role can and cannot do, asked of the framework."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.coordinator = _user(COORDINATOR, ROLE)

    def test_the_coordinator_can_triage_but_not_destroy(self):
        """Shaped for triage work without record-destroying power: read/write/create,
        no delete, no submit (the DocType is not submittable to begin with)."""
        with as_user(self.coordinator):
            for action in ("read", "write", "create"):
                self.assertTrue(
                    frappe.has_permission(DOCTYPE, action),
                    f"the coordinator must be able to {action}",
                )
            for action in ("delete", "submit"):
                self.assertFalse(
                    frappe.has_permission(DOCTYPE, action),
                    f"the coordinator must NOT be able to {action}",
                )

    def test_the_coordinator_reaches_the_confidential_field(self):
        """The permlevel-1 row exists to unlock exactly this field for the role."""
        with as_user(self.coordinator):
            fields = get_permitted_fields(DOCTYPE, permission_type="write")
        self.assertIn(
            CONFIDENTIAL_FIELD,
            fields,
            "the permlevel-1 row no longer unlocks the confidential field for the coordinator",
        )

    def test_the_existing_openers_keep_both_their_access_and_the_field(self):
        """Adding the Coordinator's rows must not disturb what System Manager,
        Accommodation Manager and Resident Supervisor already had at either
        permlevel."""
        for role in OTHER_OPENERS:
            with self.subTest(role=role):
                user = _user(
                    role.lower().replace(" ", "_") + "_rrc_perms@example.com", role
                )
                with as_user(user):
                    for action in ("read", "write"):
                        self.assertTrue(
                            frappe.has_permission(DOCTYPE, action),
                            f"{role} lost {action} on {DOCTYPE}",
                        )
                    fields = get_permitted_fields(DOCTYPE, permission_type="write")
                self.assertIn(
                    CONFIDENTIAL_FIELD,
                    fields,
                    f"{role} lost its permlevel-1 reach to {CONFIDENTIAL_FIELD}",
                )

    def test_system_manager_still_holds_delete(self):
        """The one privileged bit most at risk of being silently dropped by a
        careless permission-block edit."""
        manager = _user("system_manager_rrc_perms@example.com", "System Manager")
        with as_user(manager):
            self.assertTrue(
                frappe.has_permission(DOCTYPE, "delete"),
                "System Manager delete on Resident Request must remain",
            )
