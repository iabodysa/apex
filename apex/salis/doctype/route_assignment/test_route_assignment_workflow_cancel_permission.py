# Copyright (c) 2026, afmcoltd
"""The Route Assignment Workflow offers "Cancel" (Approved -> Cancelled, docstatus 2)
to Fleet Manager alone, but the DocType's own DocPerm carried ``cancel: 0`` for that
role — the only role the workflow ever asks to cancel could never pass the
framework's own submit/cancel gate underneath the transition, so the button the
workflow offers always raised. Proven directly against the permission the bug lived
in, not by building the full Approve chain: this is the same shape as
``apex.salis.test_salis_security``'s role-gap tests, which grade the permission a
button depends on rather than reproducing every step that reaches it.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests._helpers import _user


class TestRouteAssignmentCancelPermission(FrappeTestCase):
    def test_fleet_manager_holds_cancel_the_workflow_offers_him(self):
        frappe.set_user("Administrator")
        manager = _user("ra_cancel_fm@example.com", "Fleet Manager")
        self.assertTrue(
            frappe.has_permission("Route Assignment", "cancel", user=manager),
            "the workflow's own Cancel transition (Approved -> Cancelled) is offered "
            "only to Fleet Manager, so that role must hold cancel or the button "
            "always raises",
        )
