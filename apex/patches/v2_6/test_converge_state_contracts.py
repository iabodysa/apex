from __future__ import annotations

from unittest import TestCase
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_6 import converge_state_contracts

test_dependencies = ["Bed"]


class TestStateContractMappings(TestCase):
    def test_driver_and_maintenance_legacy_states_converge(self):
        self.assertEqual(converge_state_contracts.driver_status("On Leave"), "Stopped")
        self.assertEqual(converge_state_contracts.driver_status(None), "Stopped")
        self.assertEqual(converge_state_contracts.driver_status("Active"), "Active")
        self.assertEqual(
            converge_state_contracts.maintenance_status("Assigned"), "Open"
        )
        self.assertEqual(
            converge_state_contracts.maintenance_status("Reopened"), "Open"
        )
        self.assertEqual(
            converge_state_contracts.maintenance_status("Resolved"), "Resolved"
        )

    def test_incident_status_follows_docstatus_and_closed_is_preserved(self):
        self.assertEqual(
            converge_state_contracts.incident_status("Cancelled", 0), "Open"
        )
        self.assertEqual(
            converge_state_contracts.incident_status("Open", 1), "Under Review"
        )
        self.assertEqual(
            converge_state_contracts.incident_status("Closed", 1), "Closed"
        )
        self.assertEqual(converge_state_contracts.incident_status("Open", 2), "Closed")

    def test_unknown_states_fail_closed(self):
        with self.assertRaises(ValueError):
            converge_state_contracts.driver_status("Mystery")
        with self.assertRaises(ValueError):
            converge_state_contracts.maintenance_status("Mystery")
        with self.assertRaises(ValueError):
            converge_state_contracts.incident_status("Mystery", 1)

    def test_no_mutation_runs_when_preflight_fails(self):
        with (
            patch.object(
                converge_state_contracts,
                "_preflight",
                side_effect=ValueError("unexpected"),
            ),
            patch.object(converge_state_contracts, "_converge_rows") as converge,
        ):
            with self.assertRaises(ValueError):
                converge_state_contracts.execute()
        converge.assert_not_called()

    def test_assignment_migration_reuses_native_todo_and_is_idempotent(self):
        fake = MagicMock()
        fake.db.exists.return_value = False
        fake.as_json.side_effect = lambda value: '["user@example.com"]'
        with (
            patch.object(converge_state_contracts, "frappe", fake),
            patch.object(converge_state_contracts, "add_assignment") as add_assignment,
        ):
            converge_state_contracts._converge_maintenance_assignment(
                "MR-1", "Open", 1, "user@example.com"
            )
            fake.db.exists.return_value = True
            converge_state_contracts._converge_maintenance_assignment(
                "MR-1", "Open", 1, "user@example.com"
            )

        add_assignment.assert_called_once()

    def test_closing_a_request_retires_the_todo_and_keeps_the_assignee(self):
        """Who worked a closed ticket is history, not live state, and must survive the patch.

        Frappe's own set_status already clears ``assigned_to`` when the ToDo goes Closed
        (frappe/desk/form/assign_to.py:228-230), so an extra erase here only reaches legacy
        rows that carry an assignee with NO ToDo behind them — and for exactly those rows
        it is unrecoverable: ``frappe.db.set_value`` runs no ORM trigger
        (frappe/database/database.py:942-945) so no Version is written, and there is no
        ToDo left to read the name back from.
        """
        fake = MagicMock()
        with (
            patch.object(converge_state_contracts, "frappe", fake),
            patch.object(
                converge_state_contracts, "close_all_assignments"
            ) as close_all_assignments,
        ):
            converge_state_contracts._converge_maintenance_assignment(
                "MR-1", "Closed", 1, "tech@example.com"
            )
            converge_state_contracts._converge_maintenance_assignment(
                "MR-2", "Open", 2, "tech@example.com"
            )

        self.assertEqual(close_all_assignments.call_count, 2)
        erased = [
            call for call in fake.db.set_value.call_args_list
            if "assigned_to" in call.args
        ]
        self.assertEqual(
            erased, [],
            f"the patch erased the historical assignee: {erased}",
        )

    def test_legacy_kanban_columns_are_rewritten_to_canonical(self):
        """The other half of the kanban contract: a legacy board MUST be rewritten.

        Asserting only that a canonical board is left alone grades nothing — the rewrite
        can be deleted whole and that assertion still holds.
        """
        legacy = [
            SimpleNamespace(get=lambda key, row=row: row[key])
            for row in (
                {"column_name": "Open", "status": "Active", "indicator": "Blue", "order": "[]"},
                {"column_name": "Assigned", "status": "Active", "indicator": "Purple", "order": "[]"},
                {"column_name": "Resolved", "status": "Active", "indicator": "Green", "order": "[]"},
            )
        ]
        board = MagicMock()
        board.get.return_value = legacy
        fake = MagicMock()
        fake.db.exists.return_value = True
        fake.get_doc.return_value = board
        with patch.object(converge_state_contracts, "frappe", fake):
            converge_state_contracts._converge_maintenance_kanban()

        board.save.assert_called_once_with(ignore_permissions=True)
        self.assertEqual(
            [call.args[1]["column_name"] for call in board.append.call_args_list],
            ["Open", "In Progress", "Resolved", "Closed"],
        )

    def test_canonical_kanban_is_not_rewritten(self):
        columns = [
            SimpleNamespace(
                get=lambda key, row=row: row[key]
            )
            for row in (
                {"column_name": "Open", "status": "Active", "indicator": "Blue", "order": "[]"},
                {"column_name": "In Progress", "status": "Active", "indicator": "Orange", "order": "[]"},
                {"column_name": "Resolved", "status": "Active", "indicator": "Green", "order": "[]"},
                {"column_name": "Closed", "status": "Active", "indicator": "Gray", "order": "[]"},
            )
        ]
        board = MagicMock()
        board.get.return_value = columns
        fake = MagicMock()
        fake.db.exists.return_value = True
        fake.get_doc.return_value = board
        with patch.object(converge_state_contracts, "frappe", fake):
            converge_state_contracts._converge_maintenance_kanban()
        board.save.assert_not_called()


class TestStateContractsActuallyWrite(FrappeTestCase):
    """Every other test here mocks the database away, so the mapping functions are graded
    and the convergence itself is not: delete the ``_set_status`` calls and the suite stays
    green. These two run the real helpers against real rows and read the stored value back.
    """

    def setUp(self):
        frappe.set_user("Administrator")
        self.request = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "_Test Building",
            "room": "_T-101",
            "issue_type": "Electrical",
            "reported_by": "Administrator",
            "issue_description": "legacy state contract row",
        }).insert(ignore_permissions=True)
        self.driver = frappe.get_doc({
            "doctype": "Salis Driver",
            "naming_series": "DRV-.######",
            "full_name": "_T Legacy Driver " + frappe.generate_hash(length=12),
        }).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        # The legacy values are no longer Select options, so a legacy site is reproduced the
        # only way it can be: written past validation, exactly as the upgrade finds them.
        frappe.db.set_value(
            "Maintenance Request", self.request.name, "status", "Assigned",
            update_modified=False,
        )
        frappe.db.set_value(
            "Salis Driver", self.driver.name, "status", "On Leave", update_modified=False,
        )

    def test_legacy_maintenance_status_is_persisted_as_open(self):
        converge_state_contracts._converge_maintenance_requests()
        self.assertEqual(
            frappe.db.get_value("Maintenance Request", self.request.name, "status"),
            "Open",
            "the converged status has to reach the row, not just the mapping function",
        )

    def test_legacy_driver_status_is_persisted_as_stopped(self):
        converge_state_contracts._converge_drivers()
        self.assertEqual(
            frappe.db.get_value("Salis Driver", self.driver.name, "status"),
            "Stopped",
            "the converged status has to reach the row, not just the mapping function",
        )
