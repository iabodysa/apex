# Copyright (c) 2026, afmcoltd
"""Route Plan's ``supervisor_approval`` (and its three sibling decision fields)
carried ``allow_on_submit: 1`` with no writer anywhere in the app — a plain
``save()`` on a submitted Route Plan could still rewrite them from the desk.
Removing the flag lets the framework's own
``BaseDocument._validate_update_after_submit``
(frappe/model/base_document.py:1049-1082) refuse that edit again. Proven here
through ``insert()``/``submit()``/``save()`` only, never by calling a controller
method directly.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestRoutePlanSupervisorApprovalIsFrozenAfterSubmit(FrappeTestCase):
    def _submitted_plan(self):
        project = frappe.get_all("Project", limit=1, pluck="name")[0]
        doc = frappe.new_doc("Route Plan")
        doc.route_name = "Test Probe Route"
        doc.project = project
        doc.insert()
        doc.submit()
        return doc

    def test_editing_supervisor_approval_after_submit_is_refused(self):
        doc = self._submitted_plan()
        doc.supervisor_approval = "Approved"
        self.assertRaises(frappe.exceptions.UpdateAfterSubmitError, doc.save)
