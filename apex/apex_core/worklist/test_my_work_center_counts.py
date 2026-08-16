# Copyright (c) 2026, afmcoltd
"""A Number Card must count the whole queue, not the first page of it.

The three cards must count through ``get_list``, never by fetching rows and calling
``len()``: every read behind them is capped — 50 per DocType for the two "my documents"
cards, 200 + 100 for Pending My Action — so a ``len()`` over a capped read plateaus at the
cap and reports a number the operator has no way to know is wrong. ``frappe.db.count``
cannot substitute either: it applies neither DocPerms nor ``permission_query_conditions``,
so it would report a scoped user rows they are denied everywhere else.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import frappe

from apex.apex_core.worklist import action_inbox, my_work_center


class TestNumberCardCounts(unittest.TestCase):
    def test_a_card_counts_in_sql_and_not_over_a_capped_page(self):
        with patch.object(my_work_center, "frappe") as frappe_mock:
            frappe_mock.session.user = "u@example.com"
            frappe_mock.has_permission.return_value = True
            frappe_mock.get_list.return_value = [frappe._dict(total=137)]

            value = my_work_center.get_submitted_by_me_count()["value"]

        self.assertEqual(value, 137 * len(my_work_center.WORKLIST_REGISTRY))
        for call in frappe_mock.get_list.call_args_list:
            self.assertEqual(call.kwargs["fields"], ["count(name) as total"])
            self.assertNotIn("limit_page_length", call.kwargs)

    def test_the_count_still_goes_through_the_permissioned_reader(self):
        """``frappe.db.count`` would skip permission_query_conditions entirely."""
        with patch.object(my_work_center, "frappe") as frappe_mock:
            frappe_mock.session.user = "u@example.com"
            frappe_mock.has_permission.return_value = True
            frappe_mock.get_list.return_value = [frappe._dict(total=1)]

            my_work_center.get_approved_last_48h_count()

        frappe_mock.db.count.assert_not_called()

    def test_a_denied_doctype_contributes_nothing(self):
        with patch.object(my_work_center, "frappe") as frappe_mock:
            frappe_mock.session.user = "u@example.com"
            frappe_mock.has_permission.return_value = False

            self.assertEqual(my_work_center.get_submitted_by_me_count()["value"], 0)

        frappe_mock.get_list.assert_not_called()

    def test_the_pending_card_reads_past_the_pages_row_caps(self):
        with patch.object(action_inbox, "_pending") as pending:
            pending.return_value = {"workflow_actions": [1, 2], "todos": [3]}

            self.assertEqual(action_inbox.get_pending_action_count()["value"], 3)

        pending.assert_called_once_with(0, 0)

    def test_the_page_itself_keeps_its_render_budget(self):
        with patch.object(action_inbox, "_pending") as pending:
            action_inbox.get_pending_actions()

        pending.assert_called_once_with(
            action_inbox._PAGE_WORKFLOW_ACTIONS, action_inbox._PAGE_TODOS
        )
