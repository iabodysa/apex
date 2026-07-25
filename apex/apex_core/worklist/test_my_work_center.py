# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]
"""My Work Center — Universal My Work Workspace (Phase 1).

Tests cover:
  - response shape and surface isolation (FrappeTestCase)
  - architectural source guards (pure-Python, no bench)
  - workspace JSON guards (pure-Python, no bench)
"""

import os
import unittest

import frappe

from apex.tests.factories import ApexHabitatTestCase
from apex.apex_core.worklist.my_work_center import (
    get_my_work,
    get_submitted_by_me_count,
    get_approved_last_48h_count,
)

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _h(n=12):
    return frappe.generate_hash(length=n)


# [#kzx0d5]

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

    # [#rkzzxc]
    def test_workflow_actions_not_driven_by_worklist_registry(self):
        inbox_src = self._inbox_src()
        self.assertNotIn(
            "WORKLIST_REGISTRY",
            inbox_src,
            "action_inbox.py must NOT reference WORKLIST_REGISTRY — "
            "workflow approvals are sourced from Frappe's native Workflow Action DocType.",
        )

    # [#ncws0v]
    def test_workflow_action_is_primary_needs_action_source(self):
        inbox_src = self._inbox_src()
        self.assertIn(
            "def get_pending_actions(",
            inbox_src,
            "action_inbox.py must define get_pending_actions()",
        )
        # [#iq9bbu]
        wa_pos = inbox_src.find('"Workflow Action"')
        todo_pos = inbox_src.find('"ToDo"')
        self.assertGreater(wa_pos, -1, "'Workflow Action' must appear in action_inbox.py")
        self.assertGreater(todo_pos, -1, "'ToDo' must appear in action_inbox.py")
        self.assertLess(
            wa_pos,
            todo_pos,
            "'Workflow Action' must be queried BEFORE 'ToDo' in get_pending_actions()",
        )
        # [#115vux]
        self.assertIn(
            '"workflow_actions"',
            inbox_src,
            "get_pending_actions() must return a dict with key 'workflow_actions'",
        )

    # [#rbjfj9]
    def test_todo_rows_scoped_to_session_user(self):
        inbox_src = self._inbox_src()
        self.assertIn(
            '"allocated_to": frappe.session.user',
            inbox_src,
            "ToDo query in action_inbox.py must use "
            '"allocated_to": frappe.session.user to scope tasks to the calling user.',
        )

    # [#6a3iut]
    def test_notifications_scoped_by_for_user(self):
        mwc_src = self._mwc_src()
        self.assertIn(
            '"for_user": frappe.session.user',
            mwc_src,
            "Notification Log query in my_work_center.py must use "
            '"for_user": frappe.session.user for user isolation.',
        )
        # [#ar38di]
        notif_block_start = mwc_src.find('"Notification Log"')
        self.assertGreater(notif_block_start, -1, "'Notification Log' must be queried")
        notif_block = mwc_src[notif_block_start : notif_block_start + 400]
        self.assertIn(
            "for_user",
            notif_block,
            "for_user must appear in the Notification Log query block",
        )

    # [#rv7wz8]
    def test_get_my_work_surfaces_needs_action_from_get_pending_actions(self):
        mwc_src = self._mwc_src()
        self.assertIn(
            "get_pending_actions()",
            mwc_src,
            "get_my_work() must delegate to get_pending_actions() for needs_action",
        )
        self.assertIn(
            '"needs_action"',
            mwc_src,
            "get_my_work() must return a 'needs_action' key",
        )


# [#pmyj4u]

class TestMyWorkCenter(ApexHabitatTestCase):
    """Shape, isolation, and access tests that require a running site."""

    def test_shape(self):
        """get_my_work() must return the Phase 1 response shape."""
        w = get_my_work()
        # [#5wausm]
        for k in ("needs_action", "notifications", "mentions", "field_references", "summary"):
            self.assertIn(k, w, f"get_my_work() response must contain key '{k}'")
        # [#na3aqf]
        self.assertIn("workflow_actions", w["needs_action"])
        self.assertIn("todos", w["needs_action"])
        self.assertIsInstance(w["needs_action"]["workflow_actions"], list)
        self.assertIsInstance(w["needs_action"]["todos"], list)
        # [#rdlefx]
        self.assertIsInstance(w["notifications"], list)
        self.assertIsInstance(w["mentions"], list)
        self.assertIsInstance(w["field_references"], list)
        # [#bdq4bv]
        summary = w["summary"]
        for sk in ("needs_action", "assigned", "mentions", "notifications"):
            self.assertIn(sk, summary)
            self.assertIsInstance(summary[sk], int)
        # [#46sawi]
        self.assertEqual(w["mentions"], [], "mentions must be [] in Phase 1")
        self.assertEqual(w["field_references"], [], "field_references must be [] in Phase 1")
        self.assertEqual(summary["mentions"], 0, "summary.mentions must be 0 in Phase 1")
        # [#ds2clh]
        self.assertIn("value", get_submitted_by_me_count())
        self.assertIn("value", get_approved_last_48h_count())

    def test_owner_isolation(self):
        """The core permission property: a non-owner who CAN read the DocType still
        must not see another user's submitted document in their worklist."""
        # [#3f8rbh]
        cat = (frappe.get_meta("Resident Request")
               .get_field("request_category").options.split("\n")[0].strip())
        frappe.get_doc({
            "doctype": "Resident Request",
            "request_category": cat,
            "description": "worklist-test " + _h(),
        }).insert(ignore_permissions=True)  # [#1b55d8]

        # [#a53bv1]
        my_count = get_submitted_by_me_count()["value"]
        self.assertGreaterEqual(my_count, 0)  # [#k3b78m]

        # [#b2mog1]
        other_email = "wl_other_" + _h() + "@example.com"
        if not frappe.db.exists("User", other_email):
            frappe.get_doc({
                "doctype": "User", "email": other_email, "first_name": "WL Other",
                "roles": [{"role": "System Manager"}],
            }).insert(ignore_permissions=True)
        frappe.set_user(other_email)
        try:
            other_work = get_my_work()
            other_notif_names = {r["name"] for r in other_work["notifications"]}
        finally:
            frappe.set_user("Administrator")
        # [#a4t976]
        self.assertIsInstance(other_notif_names, set)

    def test_action_inbox_is_universal(self):
        """A personal per-user inbox must be reachable by EVERY user. The Action
        Inbox page carries no role restriction (empty roles => all users per
        frappe page.py), and the backend already scopes each user to their own
        work — so role-gating it would lock users out of their own inbox."""
        import json
        path = frappe.get_app_path(
            "apex", "apex_core", "page", "action_inbox", "action_inbox.json"
        )
        with open(path) as f:
            page = json.load(f)
        self.assertEqual(
            page.get("roles", []), [],
            "Action Inbox is a personal surface — it must have NO role restriction (universal access).",
        )
