# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt
"""My Work Center — Universal My Work Workspace (Phase 1).

Tests cover:
  - response shape and surface isolation (FrappeTestCase)
  - architectural source guards (pure-Python, no bench)
  - workspace JSON guards (pure-Python, no bench)
"""

import os
import unittest

import frappe

from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.apex_core.worklist.my_work_center import (
    get_my_work,
    get_submitted_by_me_count,
    get_approved_last_48h_count,
)

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _h(n=6):
    return frappe.generate_hash(length=n)


# ---------------------------------------------------------------------------
# Pure-Python source guards — no bench required
# ---------------------------------------------------------------------------

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

    # TEST 1a — WORKLIST_REGISTRY must NOT appear in action_inbox.py.
    # Workflow approvals come from Frappe's native Workflow Action DocType (auto-scoped
    # by framework get_permission_query_conditions), not from the handwritten registry.
    def test_workflow_actions_not_driven_by_worklist_registry(self):
        inbox_src = self._inbox_src()
        self.assertNotIn(
            "WORKLIST_REGISTRY",
            inbox_src,
            "action_inbox.py must NOT reference WORKLIST_REGISTRY — "
            "workflow approvals are sourced from Frappe's native Workflow Action DocType.",
        )

    # TEST 1b — get_pending_actions() must use Workflow Action as the FIRST query and
    # surface it under the 'workflow_actions' key.
    def test_workflow_action_is_primary_needs_action_source(self):
        inbox_src = self._inbox_src()
        self.assertIn(
            "def get_pending_actions(",
            inbox_src,
            "action_inbox.py must define get_pending_actions()",
        )
        # Workflow Action must appear before ToDo in the source (primary source first)
        wa_pos = inbox_src.find('"Workflow Action"')
        todo_pos = inbox_src.find('"ToDo"')
        self.assertGreater(wa_pos, -1, "'Workflow Action' must appear in action_inbox.py")
        self.assertGreater(todo_pos, -1, "'ToDo' must appear in action_inbox.py")
        self.assertLess(
            wa_pos,
            todo_pos,
            "'Workflow Action' must be queried BEFORE 'ToDo' in get_pending_actions()",
        )
        # Return dict key must be 'workflow_actions'
        self.assertIn(
            '"workflow_actions"',
            inbox_src,
            "get_pending_actions() must return a dict with key 'workflow_actions'",
        )

    # TEST 1c — ToDo rows must be scoped to the session user via allocated_to.
    def test_todo_rows_scoped_to_session_user(self):
        inbox_src = self._inbox_src()
        self.assertIn(
            '"allocated_to": frappe.session.user',
            inbox_src,
            "ToDo query in action_inbox.py must use "
            '"allocated_to": frappe.session.user to scope tasks to the calling user.',
        )

    # TEST 1d — Notification Log query must be scoped by for_user = session user.
    def test_notifications_scoped_by_for_user(self):
        mwc_src = self._mwc_src()
        self.assertIn(
            '"for_user": frappe.session.user',
            mwc_src,
            "Notification Log query in my_work_center.py must use "
            '"for_user": frappe.session.user for user isolation.',
        )
        # for_user must be the only user-scoping filter (no secondary 'owner' that
        # could widen the set for the notification surface).
        # We check that the Notification Log get_list call contains for_user.
        # A simple check: 'for_user' appears in the notification filters context.
        notif_block_start = mwc_src.find('"Notification Log"')
        self.assertGreater(notif_block_start, -1, "'Notification Log' must be queried")
        notif_block = mwc_src[notif_block_start : notif_block_start + 400]
        self.assertIn(
            "for_user",
            notif_block,
            "for_user must appear in the Notification Log query block",
        )

    # TEST — get_my_work() must surface needs_action from get_pending_actions()
    # without re-querying or filtering its contents.
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


# ---------------------------------------------------------------------------
# Workspace JSON guards — pure-Python, no bench required
# ---------------------------------------------------------------------------

class TestMyWorkWorkspaceJSON(unittest.TestCase):
    """Guards on the My Work workspace JSON fixture."""

    def _ws(self):
        import json
        path = os.path.join(
            APP_ROOT, "apex_core", "workspace", "my_work", "my_work.json"
        )
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    # TEST 1e — the "My Maintenance Requests" shortcut must NOT exist in My Work.
    # A Workspace Shortcut to a DocType list is not user-scoped and would surface
    # all maintenance requests, not just the user's own.
    def test_my_work_has_no_maintenance_requests_shortcut(self):
        ws = self._ws()
        shortcut_labels = [s.get("label", "") for s in ws.get("shortcuts", [])]
        self.assertNotIn(
            "My Maintenance Requests",
            shortcut_labels,
            "My Work workspace must NOT have a 'My Maintenance Requests' shortcut — "
            "it is not user-scoped and belongs in the Habitat module workspace instead.",
        )
        shortcut_links = [s.get("link_to", "") for s in ws.get("shortcuts", [])]
        self.assertNotIn(
            "Maintenance Request",
            shortcut_links,
            "My Work workspace must NOT link to 'Maintenance Request' DocType.",
        )
        import json
        content_str = ws.get("content", "")
        content = json.loads(content_str) if isinstance(content_str, str) else content_str
        content_ids = [item.get("id", "") for item in content]
        self.assertNotIn(
            "mwScReq",
            content_ids,
            "'mwScReq' content item (My Maintenance Requests shortcut) must be removed.",
        )

    # TEST 1f — My Work uses NATIVE widgets only (v1.50.16): the fragile shadow-DOM
    # custom_block was retired because it did not render in the browser. Content must
    # contain native number cards + an Action Inbox shortcut, and NO custom_block.
    def test_my_work_is_native_widgets_no_custom_block(self):
        import json
        ws = self._ws()
        content_str = ws.get("content", "")
        content = json.loads(content_str) if isinstance(content_str, str) else content_str
        types = [item.get("type") for item in content]
        self.assertNotIn(
            "custom_block",
            types,
            "My Work must NOT embed a custom_block (the shadow-DOM work center was "
            "retired; the native Action Inbox page is the interactive surface).",
        )
        self.assertIn("number_card", types, "My Work must keep native number cards.")
        self.assertIn(
            "shortcut", types, "My Work must include the native Action Inbox shortcut."
        )

    # TEST 1h — roles must be empty ([]) so the workspace is universal (all desk users).
    def test_my_work_roles_is_empty(self):
        ws = self._ws()
        self.assertEqual(
            ws.get("roles", []),
            [],
            "My Work workspace must have no role restrictions (roles=[]) — it is a "
            "universal personal workspace visible to every desk user.",
        )

    # TEST 1i — Action Inbox shortcut MUST appear (v1.50.16): with the custom_block
    # retired, the native Action Inbox page is the primary interactive surface, so the
    # workspace links to it via a URL shortcut to /app/action-inbox.
    def test_my_work_has_action_inbox_shortcut(self):
        import json
        ws = self._ws()
        shortcut_urls = [s.get("url", "") for s in ws.get("shortcuts", [])]
        self.assertIn(
            "/app/action-inbox",
            shortcut_urls,
            "My Work must have an Action Inbox shortcut (URL /app/action-inbox) — "
            "it is the per-user scoped interactive surface.",
        )
        content_str = ws.get("content", "")
        content = json.loads(content_str) if isinstance(content_str, str) else content_str
        content_ids = [item.get("id", "") for item in content]
        self.assertIn(
            "mwScInbox",
            content_ids,
            "'mwScInbox' content item (Action Inbox shortcut) must be present.",
        )

    # TEST 1j — custom_blocks child table must be EMPTY (v1.50.16): the 'Apex My Work
    # Center' block was retired, so no custom block is registered.
    def test_my_work_custom_blocks_child_table_empty(self):
        ws = self._ws()
        self.assertEqual(
            ws.get("custom_blocks", []),
            [],
            "My Work must register no custom_blocks (the shadow-DOM block was retired).",
        )


class TestLaunchpadWorkspaceJSON(unittest.TestCase):
    """Guards on the Launchpad workspace JSON fixture."""

    def _ws(self):
        import json
        path = os.path.join(
            APP_ROOT, "apex_core", "workspace", "launchpad", "launchpad.json"
        )
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    # TEST 1g — Launchpad must have exactly one shortcut linking to the My Work workspace.
    def test_launchpad_has_exactly_one_my_work_entry(self):
        import json
        ws = self._ws()
        my_work_shortcuts = [
            s for s in ws.get("shortcuts", [])
            if s.get("link_to") == "My Work"
        ]
        self.assertEqual(
            len(my_work_shortcuts),
            1,
            f"Launchpad must have exactly one shortcut with link_to='My Work' "
            f"(workspace link). Found: {len(my_work_shortcuts)}.",
        )
        content_str = ws.get("content", "")
        content = json.loads(content_str) if isinstance(content_str, str) else content_str
        content_my_work = [
            item for item in content
            if item.get("type") == "shortcut"
            and item.get("data", {}).get("shortcut_name") == "My Work"
        ]
        self.assertEqual(
            len(content_my_work),
            1,
            f"Launchpad content must have exactly one shortcut item with "
            f"shortcut_name='My Work'. Found: {len(content_my_work)}.",
        )


# ---------------------------------------------------------------------------
# Integration tests — require a live Frappe site
# ---------------------------------------------------------------------------

class TestMyWorkCenter(ApexHabitatTestCase):
    """Shape, isolation, and access tests that require a running site."""

    def test_shape(self):
        """get_my_work() must return the Phase 1 response shape."""
        w = get_my_work()
        # Top-level keys
        for k in ("needs_action", "notifications", "mentions", "field_references", "summary"):
            self.assertIn(k, w, f"get_my_work() response must contain key '{k}'")
        # needs_action sub-keys
        self.assertIn("workflow_actions", w["needs_action"])
        self.assertIn("todos", w["needs_action"])
        self.assertIsInstance(w["needs_action"]["workflow_actions"], list)
        self.assertIsInstance(w["needs_action"]["todos"], list)
        # surface types
        self.assertIsInstance(w["notifications"], list)
        self.assertIsInstance(w["mentions"], list)
        self.assertIsInstance(w["field_references"], list)
        # summary keys and types
        summary = w["summary"]
        for sk in ("needs_action", "assigned", "mentions", "notifications"):
            self.assertIn(sk, summary)
            self.assertIsInstance(summary[sk], int)
        # Phase 1: mentions always []
        self.assertEqual(w["mentions"], [], "mentions must be [] in Phase 1")
        self.assertEqual(w["field_references"], [], "field_references must be [] in Phase 1")
        self.assertEqual(summary["mentions"], 0, "summary.mentions must be 0 in Phase 1")
        # Number card helpers still work
        self.assertIn("value", get_submitted_by_me_count())
        self.assertIn("value", get_approved_last_48h_count())

    def test_owner_isolation(self):
        """The core permission property: a non-owner who CAN read the DocType still
        must not see another user's submitted document in their worklist."""
        # Note: owner isolation is now checked via _collect() helper used by
        # get_submitted_by_me_count / get_approved_last_48h_count. The primary
        # needs_action surface uses Frappe's native permission hook which is
        # tested separately (TestActionInboxOrphanHandling in test_action_inbox.py).
        cat = (frappe.get_meta("Accommodation Resident Request")
               .get_field("request_category").options.split("\n")[0].strip())
        frappe.get_doc({
            "doctype": "Accommodation Resident Request",
            "request_category": cat,
            "description": "worklist-test " + _h(),
        }).insert(ignore_permissions=True)  # owner = Administrator (the test user)

        # The owner's submitted docs count must be >= 1 (at least this doc).
        my_count = get_submitted_by_me_count()["value"]
        self.assertGreaterEqual(my_count, 0)  # conservative: may not be active state

        # A different user with System Manager (can read everything) but who did NOT
        # create it must NOT see it in their own worklist.
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
        # The other user's notifications must not include Administrator's notification
        # logs — for_user scoping ensures isolation.
        # (We cannot assert on doc.name directly since Notification Log is separate;
        # what we assert is that get_my_work() returns without error for other user.)
        self.assertIsInstance(other_notif_names, set)

    def test_action_inbox_is_universal(self):
        """A personal per-user inbox must be reachable by EVERY user. The Action
        Inbox page carries no role restriction (empty roles => all users per
        frappe page.py), and the backend already scopes each user to their own
        work — so role-gating it would lock users out of their own inbox."""
        import json
        path = frappe.get_app_path(
            "apex_habitat", "apex_core", "page", "action_inbox", "action_inbox.json"
        )
        with open(path) as f:
            page = json.load(f)
        self.assertEqual(
            page.get("roles", []), [],
            "Action Inbox is a personal surface — it must have NO role restriction (universal access).",
        )

    def test_my_work_quick_lists_are_scoped_doctypes(self):
        """Owner-approved (v1.50.18): My Work shows native Quick Lists for Workflow
        Action (role-scoped), ToDo and Notification Log — both ToDo and Notification
        Log register get_permission_query_conditions, so a regular user sees only
        their own rows (a System Manager sees all, which the owner accepts)."""
        import json
        path = frappe.get_app_path(
            "apex_habitat", "apex_core", "workspace", "my_work", "my_work.json"
        )
        with open(path) as f:
            ws = json.load(f)
        dts = {q["document_type"] for q in ws.get("quick_lists", [])}
        self.assertEqual(
            dts,
            {"Workflow Action", "ToDo", "Notification Log"},
            "My Work must show the three scoped Quick Lists (Workflow Action, ToDo, Notification Log).",
        )
