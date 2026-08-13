from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.salis import utils


class TestSalisDriverStateContract(TestCase):
    def test_approved_current_hrms_leave_blocks_an_active_driver(self):
        driver = frappe._dict(
            full_name="Driver One",
            employee="EMP-1",
            status="Active",
        )
        fake_frappe = MagicMock()
        fake_frappe.db.get_value.side_effect = [driver, "Active"]
        fake_frappe.get_all.return_value = ["HR-LAP-1"]
        with (
            patch.object(utils, "frappe", fake_frappe),
            patch.object(utils, "_", side_effect=lambda message: message),
        ):
            reason = utils.rider_block_reason("DRV-1", "2026-08-14")

        self.assertIn("HR-LAP-1", reason)
        self.assertEqual(
            fake_frappe.get_all.call_args.kwargs["filters"],
            {
                "employee": "EMP-1",
                "status": "Approved",
                "docstatus": 1,
                "from_date": ["<=", frappe.utils.getdate("2026-08-14")],
                "to_date": [">=", frappe.utils.getdate("2026-08-14")],
            },
        )

    def test_cancelled_or_expired_leave_does_not_block_an_active_driver(self):
        driver = frappe._dict(
            full_name="Driver One",
            employee="EMP-1",
            status="Active",
        )
        fake_frappe = MagicMock()
        fake_frappe.db.get_value.side_effect = [driver, "Active"]
        fake_frappe.get_all.return_value = []
        with (
            patch.object(utils, "frappe", fake_frappe),
            patch.object(utils, "_", side_effect=lambda message: message),
        ):
            self.assertIsNone(utils.rider_block_reason("DRV-1", "2026-08-14"))

    def test_driver_master_has_no_duplicate_leave_state(self):
        self.assertEqual(utils.BLOCKING_DRIVER_STATUSES, ("Stopped", "Released"))

        metadata = json.loads(
            Path(__file__).with_name("salis_driver.json").read_text(encoding="utf-8")
        )
        status = next(
            field for field in metadata["fields"] if field["fieldname"] == "status"
        )
        self.assertEqual(
            status["options"].splitlines(), ["Active", "Stopped", "Released"]
        )
        self.assertNotIn("On Leave", {state["title"] for state in metadata["states"]})
