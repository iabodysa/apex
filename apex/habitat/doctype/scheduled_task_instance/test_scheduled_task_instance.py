# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.scheduled_task_instance.scheduled_task_instance import (
    UNIQUE_KEY,
    UNIQUE_KEY_NAME,
    on_doctype_update,
)
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


def _unique_index_columns(table, index_name):
    rows = frappe.db.sql(
        """
        SELECT COLUMN_NAME AS col
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
          AND NON_UNIQUE = 0
        ORDER BY SEQ_IN_INDEX
        """,
        (table, index_name),
        as_dict=True,
    )
    return [row["col"] for row in rows]


class TestScheduledTaskInstanceUniqueKey(FrappeTestCase):
    def _instance(self, **fields):
        data = {
            "doctype": "Scheduled Task Instance",
            "naming_series": "STI-.YYYY.-.####",
            "assignment": "_T-STA-9101",
            "task_catalog": "_T-STC-9101",
            "template": "_T-STI-fake-template",
            "due_date": "2026-03-01",
        }
        data.update(fields)
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(purge_doc, "Scheduled Task Instance", doc.name)
        return doc

    def test_the_key_the_database_holds_is_the_key_the_controller_declares(self):
        on_doctype_update()
        self.assertEqual(
            _unique_index_columns("tabScheduled Task Instance", UNIQUE_KEY_NAME), UNIQUE_KEY
        )

    def test_a_second_instance_of_one_assignment_task_and_due_date_is_refused(self):
        first = self._instance()
        with self.assertRaisesRegex(frappe.UniqueValidationError, UNIQUE_KEY_NAME):
            self._instance(assignment=first.assignment, task_catalog=first.task_catalog)

    def test_the_next_due_date_of_the_same_assignment_and_task_is_accepted(self):
        first = self._instance(assignment="_T-STA-9102")
        second = self._instance(
            assignment=first.assignment,
            task_catalog=first.task_catalog,
            due_date="2026-04-01",
        )
        self.assertEqual(str(second.due_date), "2026-04-01")
