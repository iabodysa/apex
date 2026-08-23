# Copyright (c) 2026, afmcoltd

"""``_queue_document`` must not grow one new Comment per day a live alert
predicate keeps re-firing while its ToDo assignment is idempotently skipped
(``assign_role`` never re-assigns a holder who already has an open ToDo). The
comment is written only the pass a document is NEWLY queued.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.tasks import common

TARGET_DOCTYPE = "Role"
TARGET_NAME = "System Manager"


class TestQueueDocumentCommentsOnlyOnANewAssignment(FrappeTestCase):
    def setUp(self):
        self._real_assign_role = common.assign_role
        self._real_publish = common._publish_operations_alert

    def tearDown(self):
        common.assign_role = self._real_assign_role
        common._publish_operations_alert = self._real_publish

    def _comment_count(self):
        return frappe.db.count(
            "Comment",
            {"reference_doctype": TARGET_DOCTYPE, "reference_name": TARGET_NAME},
        )

    def test_no_comment_when_nobody_was_newly_assigned(self):
        common.assign_role = lambda *a, **k: 0
        common._publish_operations_alert = lambda *a, **k: None
        before = self._comment_count()

        common._queue_document(TARGET_DOCTYPE, TARGET_NAME, "Warning", "Still overdue.")

        self.assertEqual(self._comment_count(), before)

    def test_a_comment_is_written_on_a_new_assignment(self):
        common.assign_role = lambda *a, **k: 1
        common._publish_operations_alert = lambda *a, **k: None
        before = self._comment_count()

        common._queue_document(TARGET_DOCTYPE, TARGET_NAME, "Warning", "Newly overdue.")

        self.assertEqual(self._comment_count(), before + 1)
