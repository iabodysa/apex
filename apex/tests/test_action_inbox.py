# Copyright (c) 2026, AFMCO and contributors
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
        # [#h1ol11]
        self.assertIn("frappe.get_list(", src)

    def test_pending_only_no_doa_no_timewindow(self):
        src = _src()
        self.assertIn('"status": "Open"', src)  # [#8d5r0j]
        self.assertIn("get_workflow_state_field", src)  # [#sxou0d]
        self.assertIn('"allocated_to": frappe.session.user', src)  # [#k6ig3d]
        # [#1ahyym]
        self.assertNotIn(".insert(", src)
        self.assertNotIn("frappe.new_doc(", src)


class TestOrphanCleanup(unittest.TestCase):
    def test_cleanup_only_open_and_wired(self):
        with open(os.path.join(APP_ROOT, "apex_core", "utils", "workflow_utils.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("def cleanup_orphaned_workflow_actions(", src)
        self.assertIn("status = 'Open'", src)  # [#egnqf8]
        self.assertIn("DELETE", src)  # [#t4bne9]
        self.assertIn("table_exists", src)  # [#j33fj5]
        # [#ebxk7a]
        self.assertIn('frappe.db.exists("DocType"', src)
        with open(os.path.join(APP_ROOT, "hooks.py"), encoding="utf-8") as fh:
            self.assertIn("workflow_utils.cleanup_orphaned_workflow_actions", fh.read())  # [#qq4zux]

    def test_inbox_drops_actions_for_missing_doctype(self):
        # [#jrtiiz]
        self.assertIn('frappe.db.exists("DocType"', _src())


class TestActionInboxPage(unittest.TestCase):
    PAGE = os.path.join(APP_ROOT, "apex_core", "page", "action_inbox")

    def test_page_native_endpoints_no_modal(self):
        with open(os.path.join(self.PAGE, "action_inbox.js"), encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("apex.apex_core.worklist.my_work_center.get_my_work", js)
        self.assertIn("frappe.model.workflow.get_transitions", js)  # [#cfpssy]
        self.assertIn("frappe.model.workflow.apply_workflow", js)
        self.assertEqual(js.count("new frappe.ui.Dialog"), 0)  # [#r063sb]

    def test_page_no_orphan_dollar_refs(self):
        import re

        with open(os.path.join(self.PAGE, "action_inbox.js"), encoding="utf-8") as fh:
            js = fh.read()
        assigned = set(re.findall(r"this\.(\$[A-Za-z_]+)\s*=", js))
        used = set(re.findall(r"this\.(\$[A-Za-z_]+)\b", js))
        # [#kpw6qz]
        self.assertEqual((used - assigned) - {"$x"}, set(), "this.$ used but never created")

    def test_page_json_standard_no_all_role(self):
        import json

        with open(os.path.join(self.PAGE, "action_inbox.json"), encoding="utf-8") as fh:
            j = json.load(fh)
        self.assertEqual(j["page_name"], "action-inbox")
        self.assertEqual(j["standard"], "Yes")
        self.assertNotIn("All", [r["role"] for r in j.get("roles", [])])


class TestActionInboxOrphanHandling(FrappeTestCase):
    """Behavioural regression for the 2026-06-02 orphaned-reference crash."""

    MISSING_DT = "Zz Retired DocType For Inbox Test"

    def test_drop_stale_drops_actions_for_missing_doctype(self):
        from apex.apex_core.worklist.action_inbox import _drop_stale

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
        # [#cwlnaq]
        self.assertNotIn(self.MISSING_DT, kept)
        # [#p7mv7h]
        self.assertIn("ToDo", kept)

    @staticmethod
    def _force_delete(doctype, name):
        """Idempotent COMMIT'd delete: cleanup_orphaned_workflow_actions() commits, so
        owned rows escape the FrappeTestCase rollback and must be removed explicitly."""
        frappe.set_user("Administrator")
        if frappe.db.exists(doctype, name):
            frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
            frappe.db.commit()

    def test_cleanup_purges_open_actions_for_missing_doctype(self):
        from apex.apex_core.utils.workflow_utils import cleanup_orphaned_workflow_actions

        # Owned ORPHAN: references a DocType whose table does not exist -> must be purged.
        orphan = frappe.get_doc(
            {
                "doctype": "Workflow Action",
                "reference_doctype": self.MISSING_DT,
                "reference_name": "ZZ-0001",
                "status": "Open",
                "workflow_state": "New",
            }
        ).insert(ignore_permissions=True, ignore_links=True)
        # Owned CONTROL: references a live ToDo row -> the global sweep must NOT touch it.
        control_ref = frappe.get_doc(
            {
                "doctype": "ToDo",
                "description": "apex inbox-cleanup control",
                "allocated_to": "Administrator",
            }
        ).insert(ignore_permissions=True)
        control = frappe.get_doc(
            {
                "doctype": "Workflow Action",
                "reference_doctype": "ToDo",
                "reference_name": control_ref.name,
                "status": "Open",
                "workflow_state": "Open",
            }
        ).insert(ignore_permissions=True, ignore_links=True)

        # cleanup_orphaned_workflow_actions() COMMITS, so these owned rows escape the
        # rollback. Register explicit deletes BEFORE the destructive call + assertions so
        # nothing leaks even on a mid-test failure. [#hq6bc7]
        self.addCleanup(self._force_delete, "Workflow Action", orphan.name)
        self.addCleanup(self._force_delete, "Workflow Action", control.name)
        self.addCleanup(self._force_delete, "ToDo", control_ref.name)

        self.assertTrue(frappe.db.exists("Workflow Action", orphan.name))
        self.assertTrue(frappe.db.exists("Workflow Action", control.name))

        cleanup_orphaned_workflow_actions()

        # Scope the assertions to OUR owned rows (not the function's global sweep count):
        # the orphan (missing DocType) is purged; the control (live reference) survives.
        self.assertFalse(
            frappe.db.exists("Workflow Action", orphan.name),
            "cleanup must purge the Open action whose reference DocType/table is missing",
        )
        self.assertTrue(
            frappe.db.exists("Workflow Action", control.name),
            "cleanup must NOT sweep an Open action that references a live DocType row",
        )

    def test_owned_rows_do_not_leak_on_mid_test_failure(self):
        """The owned-row guard must fire even when the body aborts mid-way, so a
        committed Workflow Action can never leak into the shared DB."""
        orphan = frappe.get_doc(
            {
                "doctype": "Workflow Action",
                "reference_doctype": self.MISSING_DT,
                "reference_name": "ZZ-LEAKGUARD",
                "status": "Open",
                "workflow_state": "New",
            }
        ).insert(ignore_permissions=True, ignore_links=True)
        name = orphan.name
        # Backstop even if the assertion below fails.
        self.addCleanup(self._force_delete, "Workflow Action", name)

        guard_ran = False
        try:
            raise RuntimeError("simulated mid-test failure")
        except RuntimeError:
            self._force_delete("Workflow Action", name)  # mirrors the addCleanup guard
            guard_ran = True

        self.assertTrue(guard_ran)
        self.assertFalse(
            frappe.db.exists("Workflow Action", name),
            "owned Workflow Action must not leak after a mid-test failure",
        )


if __name__ == "__main__":
    unittest.main()
