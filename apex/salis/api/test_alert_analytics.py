# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Operations Alert resolution-latency Custom Number Card.

``get_alert_median_resolve_days`` computes the median raised->resolved span (days)
over Resolved alerts, scoped through the SAME ``_permitted_projects`` resolver the
alert queue uses. The resolver is patched at its import location in
``operations_alerts`` so the scope can be asserted deterministically on a fresh
site; alerts are provisioned in setUp with unique plates so the median is a known,
non-vacuous value.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from apex.salis.api import operations_alerts

_RESOLVER = "apex.salis.api.operations_alerts._permitted_projects"


class TestAlertMedianResolveDays(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.plate = f"MED {frappe.generate_hash(length=6)}"
        self.vehicle = (
            frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": self.plate, "status": "Active"})
            .insert(ignore_permissions=True)
            .name
        )
        # Three resolved alerts on this vehicle with spans 1, 3 and 9 days -> median 3.
        base = now_datetime() - timedelta(days=30)
        for span_days in (1, 3, 9):
            self._resolved_alert(self.vehicle, base, span_days)
        # A noise alert: resolved but missing resolved_on must NOT count.
        self._alert(self.vehicle, status="Resolved", raised_on=base, resolved_on=None)
        # A noise alert: still Open must NOT count.
        self._alert(self.vehicle, status="Open", raised_on=base, resolved_on=None)

    def _alert(self, vehicle, status, raised_on, resolved_on):
        doc = frappe.get_doc(
            {
                "doctype": "Operations Alert",
                "alert_type": "Idle Vehicle",
                "severity": "Warning",
                "message": "test",
                "vehicle": vehicle,
                "status": status,
            }
        ).insert(ignore_permissions=True)
        frappe.db.set_value(
            "Operations Alert",
            doc.name,
            {"raised_on": raised_on, "resolved_on": resolved_on},
            update_modified=False,
        )
        return doc.name

    def _resolved_alert(self, vehicle, raised_on, span_days):
        return self._alert(
            vehicle, status="Resolved", raised_on=raised_on, resolved_on=raised_on + timedelta(days=span_days)
        )

    def test_unscoped_median_is_known_value(self):
        with patch(_RESOLVER, return_value=(True, None)):
            res = operations_alerts.get_alert_median_resolve_days()
        # spans 1,3,9 -> median 3.0; noise rows (no resolved_on / still Open) excluded.
        self.assertEqual(res["value"], 3.0)
        self.assertEqual(res["fieldtype"], "Float")

    def test_scope_excludes_other_project_alerts(self):
        # Scoped to a project that does not own this vehicle: the median sees no
        # in-scope resolved alerts and returns 0, proving the vehicle-anchor scope
        # is enforced (vehicle-less / out-of-project alerts are excluded).
        ghost = f"NO-SUCH-PROJECT-{frappe.generate_hash(length=10)}"
        with patch(_RESOLVER, return_value=(False, [ghost])):
            res = operations_alerts.get_alert_median_resolve_days()
        self.assertEqual(res["value"], 0)
