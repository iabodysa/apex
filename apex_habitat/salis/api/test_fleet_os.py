"""Tests for the Fleet OS dashboard reader's typed empty reason.

get_fleet_os tells an empty board apart from an access gap: ``scope_empty`` (the
user is scoped to no project), ``data_empty`` (the permitted fleet is empty), or
``reason: None`` when vehicles are returned. The project-scope resolver is
patched so each branch is exercised deterministically on a fresh site.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import fleet_os

_RESOLVER = "apex_habitat.salis.api.fleet_os._permitted_projects"


class TestFleetOSEmptyReason(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_scope_empty_when_no_permitted_project(self):
        # Scoped user granted no project -> access gap, not an empty fleet.
        with patch(_RESOLVER, return_value=(False, [])):
            r = fleet_os.get_fleet_os()
        self.assertEqual(r["vehicles"], [])
        self.assertEqual(r["reason"], "scope_empty")

    def test_data_empty_when_scope_has_no_vehicles(self):
        # Scoped to a project that owns no vehicle -> genuinely empty board.
        ghost = f"NO-SUCH-PROJECT-{frappe.generate_hash(length=10)}"
        with patch(_RESOLVER, return_value=(False, [ghost])):
            r = fleet_os.get_fleet_os()
        self.assertEqual(r["vehicles"], [])
        self.assertEqual(r["reason"], "data_empty")

    def test_no_reason_when_vehicles_returned(self):
        plate = f"FOS {frappe.generate_hash(length=6)}"
        name = frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
        ).insert(ignore_permissions=True).name
        # Unscoped view sees the whole (non-empty) fleet -> no typed reason.
        with patch(_RESOLVER, return_value=(True, None)):
            r = fleet_os.get_fleet_os()
        self.assertIsNone(r["reason"])
        self.assertTrue(r["vehicles"])
        self.assertIn(plate, [v["plate"] for v in r["vehicles"]], name)
