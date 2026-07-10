# Copyright (c) 2026, AFMCO and contributors
"""R3 — behaviour-preservation for the Operations Alert helper redirect.

``salis.tasks._raise_alert``, ``habitat.tasks.maintenance._raise_maintenance_alert``
and ``habitat.tasks.safety._raise_safety_alert`` each used to hand-roll the
``frappe.get_doc({"doctype": "Operations Alert", ...}).insert(ignore_permissions=True)``
block. They now delegate ONLY that insert step to the shared
``apex_core.utils.operations_alert.insert_operations_alert`` while keeping their own
same-day dedupe guard (and, for maintenance, the Maintenance Request timeline comment).

These tests prove the observable Operations Alert row is unchanged (same
alert_type / severity / status / message, no vehicle/driver added or dropped) and
that each site keeps its OWN dedupe — the helper never dedupes.

The salis ``_raise_alert`` path is already covered by
``operations_alert/test_operations_alert.py::test_critical_alert_stamps_supervisor``
(the responsible_supervisor denorm) and ``tests/test_alert_dedupe_boundary.py``.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.tasks.maintenance import _raise_maintenance_alert
from apex.habitat.tasks.safety import _raise_safety_alert
from apex.tests.factories import make_building, make_company, make_room


class TestSafetyAlertRowPreserved(FrappeTestCase):
    """habitat.tasks.safety._raise_safety_alert — insert redirected to the helper."""

    def setUp(self):
        frappe.set_user("Administrator")

    def _rows(self, token):
        return frappe.get_all(
            "Operations Alert",
            filters={"alert_type": "Maintenance Overdue", "message": ["like", f"%{token}%"]},
            fields=["name", "alert_type", "severity", "status", "message", "vehicle", "driver"],
        )

    def test_row_shape_matches_legacy_insert(self):
        token = "R3-SAFETY-" + frappe.generate_hash(length=8)
        msg = f"safety breach probe {token}"
        name = _raise_safety_alert("Maintenance Overdue", "Warning", msg, token)
        self.assertTrue(name)
        self.addCleanup(
            frappe.delete_doc, "Operations Alert", name, force=True, ignore_permissions=True
        )
        rows = self._rows(token)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r.alert_type, "Maintenance Overdue")
        self.assertEqual(r.severity, "Warning")
        self.assertEqual(r.status, "Open")
        self.assertEqual(r.message, msg)
        # a safety alert carries no vehicle/driver — the redirect must not add them
        self.assertFalse(r.vehicle)
        self.assertFalse(r.driver)
        self.assertTrue(frappe.db.get_value("Operations Alert", name, "raised_on"))

    def test_own_dedupe_still_guards(self):
        token = "R3-SAFEDUP-" + frappe.generate_hash(length=8)
        msg = f"safety dup probe {token}"
        first = _raise_safety_alert("Maintenance Overdue", "Warning", msg, token)
        self.assertTrue(first)
        self.addCleanup(
            frappe.delete_doc, "Operations Alert", first, force=True, ignore_permissions=True
        )
        # a same-day repeat for the same dedupe token is suppressed (the helper never dedupes)
        second = _raise_safety_alert("Maintenance Overdue", "Warning", msg, token)
        self.assertIsNone(second)
        self.assertEqual(len(self._rows(token)), 1)

    def test_dedupe_short_circuits_before_helper(self):
        # dedupe belongs to the SITE, not the helper: when a dupe exists the site
        # returns None WITHOUT ever calling insert_operations_alert.
        token = "R3-SAFESC-" + frappe.generate_hash(length=8)
        with patch("apex.habitat.tasks.safety.frappe.db.exists", return_value=True), patch(
            "apex.habitat.tasks.safety.insert_operations_alert"
        ) as helper:
            out = _raise_safety_alert("Maintenance Overdue", "Warning", f"x {token}", token)
        self.assertIsNone(out)
        helper.assert_not_called()


class TestMaintenanceAlertRowPreserved(FrappeTestCase):
    """habitat.tasks.maintenance._raise_maintenance_alert — insert redirected; the
    timeline comment on the Maintenance Request stays local."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        make_company()
        cls.building = make_building().name
        cls.room = make_room(cls.building).name

    def setUp(self):
        frappe.set_user("Administrator")

    def _make_request(self):
        return (
            frappe.get_doc(
                {
                    "doctype": "Maintenance Request",
                    "naming_series": "MAINT-.YYYY.-.#####",
                    "building": self.building,
                    "room": self.room,
                    "reported_by": "Administrator",
                    "issue_type": "Electrical",
                    "issue_description": "R3 maintenance probe",
                }
            )
            .insert(ignore_permissions=True, ignore_links=True)
            .name
        )

    def _rows_for(self, req):
        return frappe.get_all(
            "Operations Alert",
            filters={"alert_type": "Maintenance Overdue", "message": ["like", f"%{req}%"]},
            fields=["name", "severity", "status", "message", "vehicle", "driver"],
        )

    def test_row_and_timeline_comment_preserved(self):
        req = self._make_request()
        self.addCleanup(
            frappe.delete_doc, "Maintenance Request", req, force=True, ignore_permissions=True
        )
        _raise_maintenance_alert(req, "Critical", 50.0, 24, "Electrical", "Open")
        rows = self._rows_for(req)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.addCleanup(
            frappe.delete_doc, "Operations Alert", r.name, force=True, ignore_permissions=True
        )
        # priority Critical -> severity Critical; status Open; message names the request
        self.assertEqual(r.severity, "Critical")
        self.assertEqual(r.status, "Open")
        self.assertIn(req, r.message)
        # no vehicle/driver on a maintenance alert — the redirect must not add them
        self.assertFalse(r.vehicle)
        self.assertFalse(r.driver)
        # kept-local step: the Maintenance Request timeline comment still posts
        comments = frappe.get_all(
            "Comment",
            filters={
                "reference_doctype": "Maintenance Request",
                "reference_name": req,
                "comment_type": "Comment",
            },
        )
        self.assertTrue(comments, "the maintenance alert must still post its timeline comment")

    def test_non_critical_priority_maps_to_warning_and_dedupes(self):
        req = self._make_request()
        self.addCleanup(
            frappe.delete_doc, "Maintenance Request", req, force=True, ignore_permissions=True
        )
        _raise_maintenance_alert(req, "High", 30.0, 24, "Plumbing", "Open")
        rows = self._rows_for(req)
        self.assertEqual(len(rows), 1)
        self.addCleanup(
            frappe.delete_doc, "Operations Alert", rows[0].name, force=True, ignore_permissions=True
        )
        # non-Critical priority -> Warning severity
        self.assertEqual(rows[0].severity, "Warning")
        # own dedupe: a same-day repeat for the same request inserts no second row
        _raise_maintenance_alert(req, "High", 40.0, 24, "Plumbing", "Open")
        self.assertEqual(len(self._rows_for(req)), 1)
