# Copyright (c) 2026, afmcoltd
"""Assignment on a Resident Request belongs to Frappe, not to this controller.

Two defects are held here:

* ``_assign`` was written by hand as ``[assigned_to]``, which replaced the aggregate
  ``ToDo.on_update`` -> ``update_in_reference`` builds from every live ToDo — a second
  assignee disappeared from the desk badge. Nothing in this module may write ``_assign``.
* ``status="Assigned"`` refused to save without ``assigned_to``, on a field the native
  unassign clears behind the document. That wedged every later save. ``assigned_to`` is
  read-only so the desk cannot reach that state any other way.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.habitat.doctype.resident_request import resident_request


def _raising_frappe() -> MagicMock:
    fake = MagicMock()

    def throw(message, exc=None, **_kwargs):
        raise (exc or frappe.ValidationError)(message)

    fake.throw.side_effect = throw
    fake.as_json.side_effect = json.dumps
    return fake


def _request(status, assigned_to=None, priority="Medium"):
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
        fake, add, close = self._sync(_request("Assigned", "supervisor@example.com"))

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
                fake, add, close = self._sync(_request(status, "supervisor@example.com"))
                close.assert_called_once_with("Resident Request", "RR-1")
                add.assert_not_called()
                fake.db.set_value.assert_not_called()

    def test_no_todo_is_inserted_by_hand(self):
        fake, _add, _close = self._sync(_request("Assigned", "supervisor@example.com"))
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
        doc = _request("Assigned", None)
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
