"""Guards for the Unified Action Inbox aggregation API.

Most tests are pure-Python source guards (no live site). ``TestActionInboxOrphanHandling``
adds behavioural regression coverage for the orphaned-reference crash (2026-06-02: a
retired ``Support Ticket`` left 286 Open Workflow Actions whose deleted controller made
the inbox 500 on ``get_transitions``) and needs a site (FrappeTestCase)."""

import os
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _src():
    with open(os.path.join(APP_ROOT, "apex_core", "worklist", "action_inbox.py"), encoding="utf-8") as fh:
        return fh.read()


class TestActionInboxAPI(unittest.TestCase):
    def test_aggregates_native_sources_permission_scoped(self):
        src = _src()
        self.assertIn("def get_pending_actions(", src)
        self.assertIn('"Workflow Action"', src)
        self.assertIn('"ToDo"', src)
        # Permission-scoped read for the user's pending actions: get_list, NOT get_all.
        self.assertIn("frappe.get_list(", src)

    def test_pending_only_no_doa_no_timewindow(self):
        src = _src()
        self.assertIn('"status": "Open"', src)  # only documents awaiting action
        self.assertIn("get_workflow_state_field", src)  # staleness guard, no hard-coded state field
        self.assertIn('"allocated_to": frappe.session.user', src)  # the user's own tasks only
        # Read-only aggregation: no Delegation-of-Authority / governance record is created.
        self.assertNotIn(".insert(", src)
        self.assertNotIn("frappe.new_doc(", src)


class TestOrphanCleanup(unittest.TestCase):
    def test_cleanup_only_open_and_wired(self):
        with open(os.path.join(APP_ROOT, "apex_core", "utils", "workflow_utils.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("def cleanup_orphaned_workflow_actions(", src)
        self.assertIn("status = 'Open'", src)  # acts only on Open rows
        self.assertIn("DELETE", src)  # deletes orphans (not mark-Completed → cyclic re-open stays safe)
        self.assertIn("table_exists", src)  # guarded against a since-dropped doctype
        # Case C — also purge Open actions whose reference DocType itself is gone
        # (retired/renamed); it has no active Workflow to drive the Case A/B loop.
        self.assertIn('frappe.db.exists("DocType"', src)
        with open(os.path.join(APP_ROOT, "hooks.py"), encoding="utf-8") as fh:
            self.assertIn("workflow_utils.cleanup_orphaned_workflow_actions", fh.read())  # wired daily

    def test_inbox_drops_actions_for_missing_doctype(self):
        # The inbox render-time guard must skip a reference DocType that no longer
        # exists, so the desk never calls get_transitions on a deleted controller.
        self.assertIn('frappe.db.exists("DocType"', _src())


class TestActionInboxPage(unittest.TestCase):
    PAGE = os.path.join(APP_ROOT, "apex_core", "page", "action_inbox")

    def test_page_native_endpoints_no_modal(self):
        with open(os.path.join(self.PAGE, "action_inbox.js"), encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("apex_habitat.apex_core.worklist.action_inbox.get_pending_actions", js)
        self.assertIn("frappe.model.workflow.get_transitions", js)  # inline actions via native endpoints
        self.assertIn("frappe.model.workflow.apply_workflow", js)
        self.assertEqual(js.count("new frappe.ui.Dialog"), 0)  # inline, no modal

    def test_page_no_orphan_dollar_refs(self):
        import re

        with open(os.path.join(self.PAGE, "action_inbox.js"), encoding="utf-8") as fh:
            js = fh.read()
        assigned = set(re.findall(r"this\.(\$[A-Za-z_]+)\s*=", js))
        used = set(re.findall(r"this\.(\$[A-Za-z_]+)\b", js))
        # $x appears only inside the rule's comment, not as a real container.
        self.assertEqual((used - assigned) - {"$x"}, set(), "this.$ used but never created")

    def test_page_json_standard_no_all_role(self):
        import json

        with open(os.path.join(self.PAGE, "action_inbox.json"), encoding="utf-8") as fh:
            j = json.load(fh)
        self.assertEqual(j["page_name"], "action-inbox")
        self.assertEqual(j["standard"], "Yes")
        self.assertNotIn("All", [r["role"] for r in j.get("roles", [])])

    def test_page_wired_into_workspace(self):
        import json

        with open(
            os.path.join(APP_ROOT, "apex_core", "workspace", "apex_core", "apex_core.json"), encoding="utf-8"
        ) as fh:
            ws = json.load(fh)
        self.assertTrue(any(s.get("link_to") == "action-inbox" for s in ws.get("shortcuts", [])))
        self.assertIn("acScActionInbox", ws.get("content", ""))  # also placed in the content layout


class TestActionInboxOrphanHandling(FrappeTestCase):
    """Behavioural regression for the 2026-06-02 orphaned-reference crash."""

    MISSING_DT = "Zz Retired DocType For Inbox Test"

    def test_drop_stale_drops_actions_for_missing_doctype(self):
        from apex_habitat.apex_core.worklist.action_inbox import _drop_stale

        rows = [
            {
                "name": "wa-orphan",
                "reference_doctype": self.MISSING_DT,
                "reference_name": "ZZ-0001",
                "workflow_state": "New",
                "creation": "2026-01-01 00:00:00",
            },
            {
                "name": "wa-real",
                "reference_doctype": "ToDo",
                "reference_name": "x",
                "workflow_state": "Open",
                "creation": "2026-01-01 00:00:00",
            },
        ]
        kept = {r["reference_doctype"] for r in _drop_stale(rows)}
        # orphaned-doctype action dropped → the desk never imports a deleted controller
        self.assertNotIn(self.MISSING_DT, kept)
        # a real doctype with no workflow is still kept (conservative behaviour preserved)
        self.assertIn("ToDo", kept)

    def test_cleanup_purges_open_actions_for_missing_doctype(self):
        from apex_habitat.apex_core.utils.workflow_utils import cleanup_orphaned_workflow_actions

        wa = frappe.get_doc(
            {
                "doctype": "Workflow Action",
                "reference_doctype": self.MISSING_DT,
                "reference_name": "ZZ-0001",
                "status": "Open",
                "workflow_state": "New",
            }
        ).insert(ignore_permissions=True, ignore_links=True)
        self.assertTrue(frappe.db.exists("Workflow Action", wa.name))
        cleanup_orphaned_workflow_actions()  # Case C sweeps reference DocTypes that are gone
        self.assertFalse(frappe.db.exists("Workflow Action", wa.name))


if __name__ == "__main__":
    unittest.main()
