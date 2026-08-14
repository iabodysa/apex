from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.salis import utils
from apex.salis.doctype.salis_driver import salis_driver


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

    def test_leave_query_failure_blocks_the_operation(self):
        with patch.object(
            utils.frappe,
            "get_all",
            side_effect=RuntimeError("database unavailable"),
        ):
            with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                utils._approved_leave_on("EMP-1", "2026-08-14")

    def test_driver_status_is_server_owned(self):
        new_doc = MagicMock(status="Released")
        new_doc.is_new.return_value = True
        salis_driver.SalisDriver._refuse_a_hand_written_status(new_doc)
        self.assertEqual(new_doc.status, "Active")

        existing = MagicMock()
        existing.is_new.return_value = False
        existing.has_value_changed.return_value = True
        fake_frappe = MagicMock()
        fake_frappe.PermissionError = frappe.PermissionError
        fake_frappe.throw.side_effect = lambda message, exc=None: (_ for _ in ()).throw(
            (exc or frappe.ValidationError)(message)
        )
        with (
            patch.object(salis_driver, "frappe", fake_frappe),
            patch.object(salis_driver, "_", side_effect=lambda message: message),
            self.assertRaises(frappe.PermissionError),
        ):
            salis_driver.SalisDriver._refuse_a_hand_written_status(existing)

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
        self.assertTrue(status["read_only"])
        self.assertNotIn("On Leave", {state["title"] for state in metadata["states"]})
