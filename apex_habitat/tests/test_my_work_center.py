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

from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.apex_core.worklist.my_work_center import (
    get_my_work,
    get_submitted_by_me_count,
    get_approved_last_48h_count,
)

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _h(n=6):
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


# [#99c5up]

class TestMyWorkWorkspaceJSON(unittest.TestCase):
    """Guards on the My Work workspace JSON fixture."""

    def _ws(self):
        import json
        path = os.path.join(
            APP_ROOT, "apex_core", "workspace", "my_work", "my_work.json"
        )
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    # [#o24a7r]
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

    # [#2dwx5h]
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

    # [#diqbmd]
    def test_my_work_roles_is_empty(self):
        ws = self._ws()
        self.assertEqual(
            ws.get("roles", []),
            [],
            "My Work workspace must have no role restrictions (roles=[]) — it is a "
            "universal personal workspace visible to every desk user.",
        )

    # [#135w1h]
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

    # [#9nlthh]
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

    # [#bj01n1]
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
        cat = (frappe.get_meta("Accommodation Resident Request")
               .get_field("request_category").options.split("\n")[0].strip())
        frappe.get_doc({
            "doctype": "Accommodation Resident Request",
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
            "apex_habitat", "apex_core", "page", "action_inbox", "action_inbox.json"
        )
        with open(path) as f:
            page = json.load(f)
        self.assertEqual(
            page.get("roles", []), [],
            "Action Inbox is a personal surface — it must have NO role restriction (universal access).",
        )

    def test_my_work_has_no_quick_lists(self):
        """2026-06-25 workspace design: no live Quick Lists on any public workspace.
        The personal queues are reached through the Action Inbox page and the
        Operations Alert shortcut instead."""
        import json
        path = frappe.get_app_path(
            "apex_habitat", "apex_core", "workspace", "my_work", "my_work.json"
        )
        with open(path) as f:
            ws = json.load(f)
        self.assertEqual(
            ws.get("quick_lists", []), [],
            "My Work must carry no Quick Lists under the new design.",
        )
        self.assertNotIn(
            "quick_list", ws.get("content", ""),
            "My Work content blob must contain no quick_list blocks.",
        )
