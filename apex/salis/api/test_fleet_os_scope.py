# Copyright (c) 2026, afmcoltd
"""Why the fleet board is empty, and the difference between the two reasons.

An empty board means one of two things and the operator must be told which: no project is in scope
at all, or the scope is real and holds no vehicle. The third case proves a vehicle in scope clears
the reason entirely — and it borrows the fixture vehicle rather than minting one.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import fleet_os

test_dependencies = ["Salis Vehicle"]

RESOLVER = "apex.salis.api.fleet_reader._permitted_projects"
FIXTURE_PLATE = "_T ABC 1001"


class TestFleetBoardEmptyReason(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_no_project_in_scope_reads_as_scope_empty(self):
        with patch(RESOLVER, return_value=(False, [])):
            board = fleet_os.get_fleet_os()

        self.assertEqual(board["vehicles"], [])
        self.assertEqual(board["reason"], "scope_empty")

    def test_a_real_scope_holding_no_vehicle_reads_as_data_empty(self):
        absent = f"NO-SUCH-PROJECT-{frappe.generate_hash(length=12)}"

        with patch(RESOLVER, return_value=(False, [absent])):
            board = fleet_os.get_fleet_os()

        self.assertEqual(board["vehicles"], [])
        self.assertEqual(board["reason"], "data_empty")

    def test_a_vehicle_in_scope_leaves_no_reason_at_all(self):
        with patch(RESOLVER, return_value=(True, None)):
            board = fleet_os.get_fleet_os()

        self.assertIsNone(board["reason"])
        self.assertIn(FIXTURE_PLATE, [row["plate"] for row in board["vehicles"]])
