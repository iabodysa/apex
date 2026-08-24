# Copyright (c) 2026, afmcoltd
"""Tests for Maintenance Work Order's planned-date-order guard.

Patterned on frappe/tests/test_document.py. The row is built directly and
inserted so the module-level ``validate`` in ``maintenance_work_order.py``
-- wired through hooks.py's doc_events, not the class body -- is what is
exercised, not a stub.

``Maintenance Request`` is excluded from the dependency walk: no case here
sets a real one (``ignore_links``), and its own closure resolves an
unmigrated ``Payment Gateway`` and kills record-building before a single
test runs.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_ignore = ["Maintenance Request"]


class TestMaintenanceWorkOrderDateGuard(FrappeTestCase):
    def test_a_planned_end_date_before_the_start_date_is_refused(self):
        doc = frappe.get_doc(
            {
                "doctype": "Maintenance Work Order",
                "maintenance_request": "_T-MWO-fake-request",
                "planned_start_date": "2026-06-01",
                "planned_end_date": "2026-01-01",
                "work_description": "_T-Guard check",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)
