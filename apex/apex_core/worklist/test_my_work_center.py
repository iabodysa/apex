# Copyright (c) 2026, afmcoltd
"""My Work Center — Universal My Work Workspace (Phase 1).

Tests cover:
  - response shape and surface isolation (FrappeTestCase)
  - architectural source guards (pure-Python, no bench)
  - the Action Inbox page's universal-access contract (pure-Python)

``ApexHabitatTestCase`` is gone from here: it is an empty subclass of ``FrappeTestCase``
carried by ``apex/tests/factories.py``, so importing the 37KB factory module bought this
file nothing but the import. The one identity the isolation case needs comes from the
shared ``_user`` get-or-create, and the Resident Request it files is the subject.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

import apex
from apex.apex_core.worklist.my_work_center import (
    get_approved_last_48h_count,
    get_my_work,
    get_submitted_by_me_count,
)
from apex.tests._helpers import _user, as_user

# Two levels up, not one: this test sits in apex/apex_core/worklist/, so APP_ROOT is the
# apex package. A relocation that leaves this at ".." silently builds
# apex/apex_core/apex_core/... and every source read raises FileNotFoundError.
APP_ROOT = str(Path(apex.__file__).resolve().parent)


class TestMyWorkCenterSourceGuards(unittest.TestCase):
    """Architectural boundary guards: assert correct sourcing without a live site."""

    def _mwc_src(self):
        with open(
            os.path.join(APP_ROOT, "apex_core", "worklist", "my_work_center.py"),
            encoding="utf-8",
        ) as fh:
            return fh.read()

    def _inbox_src(self):
        with open(
            os.path.join(APP_ROOT, "apex_core", "worklist", "action_inbox.py"),
            encoding="utf-8",
        ) as fh:
            return fh.read()

    def test_workflow_actions_not_driven_by_worklist_registry(self):
        self.assertNotIn(
            "WORKLIST_REGISTRY",
            self._inbox_src(),
            "action_inbox.py must NOT reference WORKLIST_REGISTRY — workflow approvals are "
            "sourced from Frappe's native Workflow Action DocType.",
        )

    def test_workflow_action_is_primary_needs_action_source(self):
        inbox_src = self._inbox_src()
        self.assertIn(
            "def get_pending_actions(", inbox_src, "action_inbox.py must define get_pending_actions()"
        )
        wa_pos = inbox_src.find('"Workflow Action"')
        todo_pos = inbox_src.find('"ToDo"')
        self.assertGreater(wa_pos, -1, "'Workflow Action' must appear in action_inbox.py")
        self.assertGreater(todo_pos, -1, "'ToDo' must appear in action_inbox.py")
        self.assertLess(
            wa_pos,
            todo_pos,
            "'Workflow Action' must be queried BEFORE 'ToDo' in get_pending_actions()",
        )
        self.assertIn(
            '"workflow_actions"',
            inbox_src,
            "get_pending_actions() must return a dict with key 'workflow_actions'",
        )

    def test_todo_rows_scoped_to_session_user(self):
        self.assertIn(
            '"allocated_to": frappe.session.user',
            self._inbox_src(),
            'ToDo query in action_inbox.py must use "allocated_to": frappe.session.user to '
            "scope tasks to the calling user.",
        )

    def test_notifications_scoped_by_for_user(self):
        mwc_src = self._mwc_src()
        self.assertIn(
            '"for_user": frappe.session.user',
            mwc_src,
            'Notification Log query in my_work_center.py must use "for_user": '
            "frappe.session.user for user isolation.",
        )
        notif_block_start = mwc_src.find('"Notification Log"')
        self.assertGreater(notif_block_start, -1, "'Notification Log' must be queried")
        notif_block = mwc_src[notif_block_start : notif_block_start + 400]
        self.assertIn(
            "for_user", notif_block, "for_user must appear in the Notification Log query block"
        )

    def test_get_my_work_surfaces_needs_action_from_get_pending_actions(self):
        mwc_src = self._mwc_src()
        self.assertIn(
            "get_pending_actions()",
            mwc_src,
            "get_my_work() must delegate to get_pending_actions() for needs_action",
        )
        self.assertIn(
            '"needs_action"', mwc_src, "get_my_work()'s summary must carry a 'needs_action' count"
        )

    def test_action_inbox_is_universal(self):
        """A personal per-user inbox must be reachable by EVERY user. The Action Inbox page
        carries no role restriction (empty roles => all users per frappe page.py), and the
        backend already scopes each user to their own work — so role-gating it would lock
        users out of their own inbox."""
        with open(
            os.path.join(APP_ROOT, "apex_core", "page", "action_inbox", "action_inbox.json"),
            encoding="utf-8",
        ) as fh:
            page = json.load(fh)
        self.assertEqual(
            page.get("roles", []),
            [],
            "Action Inbox is a personal surface — it must have NO role restriction "
            "(universal access).",
        )


class TestMyWorkCenter(FrappeTestCase):
    """Shape and isolation tests that require a running site."""

    def test_shape(self):
        """get_my_work() must return the six sections the Action Inbox page renders.

        The pre-conversion form of this case asserted a Phase 1 shape — ``needs_action``,
        ``mentions``, ``field_references`` — that ``get_my_work`` has not returned for some
        time. It was never run, so nobody could know.
        """
        w = get_my_work()
        for key in (
            "awaiting_action",
            "my_open_submitted",
            "my_recent_closed",
            "acted_on_my_documents",
            "my_notifications",
            "summary",
        ):
            self.assertIn(key, w, f"get_my_work() response must contain key '{key}'")

        for key in (
            "my_open_submitted",
            "my_recent_closed",
            "acted_on_my_documents",
            "my_notifications",
        ):
            self.assertIsInstance(w[key], list, f"'{key}' must be a list of rows")

        self.assertIn("workflow_actions", w["awaiting_action"])
        self.assertIn("todos", w["awaiting_action"])
        self.assertIsInstance(w["awaiting_action"]["workflow_actions"], list)
        self.assertIsInstance(w["awaiting_action"]["todos"], list)

        summary = w["summary"]
        for key in ("needs_action", "assigned", "acted_on_my_documents", "notifications"):
            self.assertIn(key, summary)
            self.assertIsInstance(summary[key], int)
        self.assertEqual(
            summary["needs_action"],
            len(w["awaiting_action"]["workflow_actions"]) + len(w["awaiting_action"]["todos"]),
            "the badge count must be the two awaiting-action queues, not a separate query",
        )
        self.assertEqual(summary["assigned"], len(w["awaiting_action"]["todos"]))
        self.assertEqual(summary["acted_on_my_documents"], len(w["acted_on_my_documents"]))

        self.assertIn("value", get_submitted_by_me_count())
        self.assertIn("value", get_approved_last_48h_count())

    def test_owner_isolation(self):
        """The core permission property: a non-owner who CAN read the DocType still must
        not see another user's submitted document in their worklist.

        The pre-conversion form of this case ended on ``assertIsInstance(..., set)``, which
        holds whatever the counter returns — it could not have caught a leak. It asserts the
        count now: Administrator files a Resident Request, and the other System Manager's
        own count must not move because of it.
        """
        other = _user("wl_other@example.com", "System Manager")

        with as_user(other):
            before = get_submitted_by_me_count()["value"]

        category = (
            frappe.get_meta("Resident Request")
            .get_field("request_category")
            .options.split("\n")[0]
            .strip()
        )
        frappe.get_doc(
            {
                "doctype": "Resident Request",
                "request_category": category,
                "description": "worklist-test " + frappe.generate_hash(length=12),
            }
        ).insert(ignore_permissions=True)

        self.assertGreaterEqual(get_submitted_by_me_count()["value"], 0)

        with as_user(other):
            self.assertEqual(
                get_submitted_by_me_count()["value"],
                before,
                "another user's document must never enter this user's worklist count",
            )
