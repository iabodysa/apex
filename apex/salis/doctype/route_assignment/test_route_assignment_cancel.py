# Copyright (c) 2026, afmcoltd
"""Regression: cancelling a Route Assignment withdraws the trips it generated.

``on_submit`` calls ``generate_for_assignment``, which inserts up to fourteen days of
draft Dispatch Trips AND stamps ``generated_through``. The class carried no
``on_cancel``, so a cancelled recurrence left every generated trip live on the
dispatch board — a shift nobody had approved any more, with the Transport Requests
each draft had claimed still locked to it.

Three things are asserted, and the second and third are the ones a naive fix misses:

* a draft trip still at Planned is deleted (``on_trash`` is what releases its claimed
  requests, so it must be a delete and not a status edit);
* a SUBMITTED trip is left alone — it has been dispatched or completed, and cancelling
  a recurrence must not rewrite an operational record;
* ``generated_through`` is cleared, or an amendment copies the watermark forward and
  skips regenerating the very days that were just deleted.

Pure unit tests: the controller's ``frappe`` handle is replaced, so no site and no rows.
"""

from __future__ import annotations

import unittest
from unittest import mock

from apex.salis.doctype.route_assignment.route_assignment import RouteAssignment


ASSIGNMENT = "RA-1"


def _cancel(generated=("DT-1", "DT-2")):
    """Run ``on_cancel`` on a stand-in and report what it asked frappe to do."""
    doc = mock.Mock(spec=RouteAssignment)
    doc.name = ASSIGNMENT

    mock_frappe = mock.MagicMock()
    mock_frappe.get_all.return_value = list(generated)

    with mock.patch(
        "apex.salis.doctype.route_assignment.route_assignment.frappe", mock_frappe
    ):
        RouteAssignment.on_cancel(doc)
    return doc, mock_frappe


class TestRouteAssignmentCancel(unittest.TestCase):
    def test_generated_draft_trips_are_deleted(self):
        _doc, mock_frappe = _cancel()
        deleted = [call.args[1] for call in mock_frappe.delete_doc.call_args_list]
        self.assertEqual(["DT-1", "DT-2"], deleted)

    def test_only_this_assignments_unrun_drafts_are_selected(self):
        _doc, mock_frappe = _cancel()
        filters = mock_frappe.get_all.call_args.kwargs["filters"]
        self.assertEqual(ASSIGNMENT, filters["route_assignment"])
        self.assertEqual(0, filters["docstatus"])
        self.assertEqual("Planned", filters["status"])

    def test_the_delete_carries_no_permission_bypass(self):
        """Fleet Manager owns both the Cancel transition and delete on Dispatch Trip,
        so the acting user's own rights carry this — there is no need to bypass."""
        _doc, mock_frappe = _cancel()
        for call in mock_frappe.delete_doc.call_args_list:
            self.assertNotIn("ignore_permissions", call.kwargs)
            self.assertNotIn("force", call.kwargs)

    def test_the_generation_watermark_is_cleared(self):
        doc, _mock_frappe = _cancel()
        doc.db_set.assert_called_once_with("generated_through", None)

    def test_nothing_generated_still_clears_the_watermark(self):
        doc, mock_frappe = _cancel(generated=())
        mock_frappe.delete_doc.assert_not_called()
        doc.db_set.assert_called_once_with("generated_through", None)


if __name__ == "__main__":
    unittest.main()
