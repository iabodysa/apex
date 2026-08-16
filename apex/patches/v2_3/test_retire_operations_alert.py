# Copyright (c) 2026, AFMCO and contributors
"""Tests for the retired Operations Alert reader cleanup.

The retired ``Operations Alert`` DocType itself is gone from every current
site (this patch's own table-drop already ran), so what remains testable on
any site is its OWN readers: the patch must delete each exact
``READER_RECORDS`` name regardless of doctype, and it must not raise when the
table it also tries to drop no longer exists (asserted implicitly: this test
runs on a site with no ``Operations Alert`` table and does not error).
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_3.retire_operations_alert import READER_RECORDS, execute


class TestRetireOperationsAlertReaders(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._existed = {}
        for doctype, name in READER_RECORDS:
            self._existed[(doctype, name)] = frappe.db.exists(doctype, name)
            if self._existed[(doctype, name)]:
                continue
            self._create(doctype, name)

    def tearDown(self):
        # execute() already removed everything it should have; nothing to undo.
        pass

    def _create(self, doctype, name):
        if doctype == "Notification":
            frappe.get_doc(
                {
                    "doctype": "Notification",
                    "name": name,
                    "subject": name,
                    "document_type": "ToDo",
                    "event": "New",
                    "channel": "System Notification",
                }
            ).insert(ignore_permissions=True)
        elif doctype == "Number Card":
            frappe.get_doc(
                {
                    "doctype": "Number Card",
                    "name": name,
                    "label": name,
                    "type": "Document Type",
                    "document_type": "ToDo",
                    "function": "Count",
                }
            ).insert(ignore_permissions=True)
        elif doctype == "Dashboard Chart":
            frappe.get_doc(
                {
                    "doctype": "Dashboard Chart",
                    "chart_name": name,
                    "chart_type": "Count",
                    "document_type": "ToDo",
                    "based_on": "creation",
                    "type": "Line",
                    "timespan": "Last Month",
                    "time_interval": "Daily",
                    "filters_json": "[]",
                }
            ).insert(ignore_permissions=True)
        else:
            raise AssertionError(f"unhandled reader doctype in this test: {doctype}")

    def test_execute_removes_every_reader_record(self):
        for doctype, name in READER_RECORDS:
            self.assertTrue(
                frappe.db.exists(doctype, name), f"test fixture setup failed for {doctype} {name}"
            )

        execute()

        for doctype, name in READER_RECORDS:
            self.assertFalse(
                frappe.db.exists(doctype, name), f"{doctype} {name} survived the retirement patch"
            )

    def test_execute_does_not_raise_when_the_retired_table_is_already_gone(self):
        self.assertFalse(frappe.db.table_exists("Operations Alert"))
        execute()  # must not raise
