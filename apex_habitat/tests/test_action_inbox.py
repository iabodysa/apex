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


if __name__ == "__main__":
    unittest.main()
