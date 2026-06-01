"""Pure-Python guards for the Unified Action Inbox aggregation API (no live site)."""

import os
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _src():
    with open(os.path.join(APP_ROOT, "apex_core", "action_inbox.py"), encoding="utf-8") as fh:
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
        with open(os.path.join(APP_ROOT, "workflow_utils.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("def cleanup_orphaned_workflow_actions(", src)
        self.assertIn("status = 'Open'", src)  # acts only on Open rows
        self.assertIn("DELETE", src)  # deletes orphans (not mark-Completed → cyclic re-open stays safe)
        self.assertIn("table_exists", src)  # guarded against a since-dropped doctype
        with open(os.path.join(APP_ROOT, "hooks.py"), encoding="utf-8") as fh:
            self.assertIn("workflow_utils.cleanup_orphaned_workflow_actions", fh.read())  # wired daily


class TestActionInboxPage(unittest.TestCase):
    PAGE = os.path.join(APP_ROOT, "apex_core", "page", "action_inbox")

    def test_page_native_endpoints_no_modal(self):
        with open(os.path.join(self.PAGE, "action_inbox.js"), encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("apex_habitat.apex_core.action_inbox.get_pending_actions", js)
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


if __name__ == "__main__":
    unittest.main()
