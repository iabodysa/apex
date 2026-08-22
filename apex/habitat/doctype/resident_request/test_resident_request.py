# Copyright (c) 2026, afmcoltd
"""What a Resident Request guarantees, asserted against the DocType itself.

Patterned on frappe's own document-validation tests (``frappe/tests/test_document.py``)
for the ``validate``/status-transition guarantees, and on ``frappe/tests/test_assign.py``
for the native ToDo follow-up ``on_update`` drives through frappe's own assignment API.

Not submittable — every guarantee here lives in ``before_insert``, ``validate`` and
``on_update``, all wired as module-level functions through ``hooks.py``'s ``doc_events``
(confirmed there; the ``ResidentRequest`` class itself is empty), so each is only ever
exercised through ``insert()`` / ``save()``, never called directly.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["QR Location"]


class TestResidentRequest(FrappeTestCase):
    def test_a_website_field_honeypot_submission_is_refused(self):
        """The public QR web form's honeypot: a hidden ``website_field`` value means a bot
        filled in a field no human visitor sees. Checked in ``validate``, not only the
        hardened endpoint beside it, because the plain web form save path never touches
        that endpoint at all."""
        request = frappe.new_doc("Resident Request")
        request.request_category = "Maintenance"
        request.description = "_T-normal submission text"
        request.website_field = "spam"

        with self.assertRaisesRegex(frappe.PermissionError, "Invalid submission"):
            request.insert()

    def test_a_submission_without_the_honeypot_field_is_accepted(self):
        """The acceptance counterpart to the refusal above — an ordinary submission using
        the same two mandatory fields every other case in this suite relies on must still
        go through."""
        request = frappe.new_doc("Resident Request")
        request.request_category = "Maintenance"
        request.description = "_T-normal submission text"

        request.insert()

        self.assertTrue(request.name)

    def test_an_ac_keyword_description_is_escalated_to_high_priority(self):
        """``_apply_priority_rules`` reads category and description together; a resident
        stuck without air conditioning must not wait behind a filed-and-forgotten Low
        priority ticket. The standing fixture's own description ("AC not cooling") is the
        keyword match."""
        request = frappe.copy_doc(frappe.get_test_records("Resident Request")[0])

        request.insert()

        self.assertEqual(request.priority, "High")

    def test_an_unresolvable_location_token_is_refused(self):
        """A token that resolves to no active QR Location must not silently leave the
        request unlocated — refused outright instead."""
        request = frappe.new_doc("Resident Request")
        request.request_category = "Maintenance"
        request.description = "_T-broken tap"
        request.location_token = "_T-nonexistent-token"

        with self.assertRaisesRegex(
            frappe.ValidationError, "Invalid or inactive location token"
        ):
            request.insert()

    def test_a_valid_qr_locations_token_populates_the_requests_location(self):
        """The acceptance counterpart: a token matching an active QR Location must
        populate the building and room from it, the whole point of the QR poster."""
        token = frappe.db.get_value(
            "QR Location", {"poster_title": "_T-Front Gate Poster"}, "location_token"
        )
        request = frappe.new_doc("Resident Request")
        request.request_category = "Maintenance"
        request.description = "_T-broken tap near the gate"
        request.location_token = token

        request.insert()

        self.assertEqual(request.building, "_Test Building")
        self.assertEqual(request.room, "_T-101")

    def test_closing_a_request_without_resolution_notes_is_refused(self):
        """A request closed with no record of how it was resolved leaves nothing for the
        next person to read."""
        request = frappe.new_doc("Resident Request")
        request.request_category = "Complaint"
        request.description = "_T-noise complaint"
        request.status = "Closed"

        with self.assertRaisesRegex(
            frappe.ValidationError, "Resolution Notes are required"
        ):
            request.insert()

    def test_closing_a_request_with_resolution_notes_stamps_closed_on_and_closed_by(self):
        """The acceptance counterpart — a stated resolution must still let the request
        close, and close/who fields are stamped automatically rather than left for the
        closer to fill in by hand."""
        request = frappe.new_doc("Resident Request")
        request.request_category = "Complaint"
        request.description = "_T-noise complaint resolved"
        request.status = "Closed"
        request.resolution_notes = "_T-Mediated between both rooms"

        request.insert()

        self.assertEqual(request.closed_on, frappe.utils.today())
        self.assertEqual(request.closed_by, frappe.session.user)

    def test_a_status_of_assigned_without_an_assignee_reverts_to_new(self):
        """"Assigned" with nobody named to it is a contradiction the request cannot hold;
        it is quietly corrected back to New rather than left in a state no queue reads."""
        request = frappe.new_doc("Resident Request")
        request.request_category = "Maintenance"
        request.description = "_T-leaking pipe"
        request.status = "Assigned"

        request.insert()

        self.assertEqual(request.status, "New")

    def test_assigning_a_request_creates_a_todo_and_closing_it_closes_the_todo(self):
        """``on_update``'s native ToDo follow-up: an Assigned request must put itself in
        the assignee's desk queue, and ending the request must close that ToDo rather than
        leaving a stale item behind — driven through frappe's own assignment API, not the
        ToDo table directly."""
        request = frappe.new_doc("Resident Request")
        request.request_category = "Maintenance"
        request.description = "_T-broken chair"
        request.status = "Assigned"
        request.assigned_to = "Administrator"
        request.insert()

        self.assertTrue(
            frappe.db.exists(
                "ToDo",
                {
                    "reference_type": "Resident Request",
                    "reference_name": request.name,
                    "allocated_to": "Administrator",
                    "status": "Open",
                },
            )
        )

        request.status = "Resolved"
        request.resolution_notes = "_T-Chair repaired"
        request.save()

        self.assertFalse(
            frappe.db.exists(
                "ToDo",
                {
                    "reference_type": "Resident Request",
                    "reference_name": request.name,
                    "status": "Open",
                },
            )
        )
