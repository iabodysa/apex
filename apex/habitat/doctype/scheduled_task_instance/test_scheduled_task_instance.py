# Copyright (c) 2026, afmcoltd
"""Tests for Scheduled Task Instance's cancellation-reason guard.

Patterned on frappe/tests/test_document.py for the cancel guard. The row is
built, submitted and cancelled so the module-level ``before_cancel`` in
``scheduled_task_instance.py`` -- wired through hooks.py's doc_events, not
the class body -- is what is exercised, not a stub.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import purge_doc


class TestScheduledTaskInstanceCancelGuard(FrappeTestCase):
    def test_cancelling_without_a_reason_is_refused(self):
        doc = frappe.get_doc(
            {
                "doctype": "Scheduled Task Instance",
                "naming_series": "STI-.YYYY.-.####",
                "template": "_T-STI-fake-template",
                "due_date": "2026-03-01",
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        doc.submit()
        self.addCleanup(purge_doc, "Scheduled Task Instance", doc.name)
        with self.assertRaises(frappe.ValidationError):
            doc.cancel()
