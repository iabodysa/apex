# Copyright (c) 2026, afmcoltd

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
