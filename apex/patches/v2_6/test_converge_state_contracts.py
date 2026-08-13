from __future__ import annotations

from unittest import TestCase
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apex.patches.v2_6 import converge_state_contracts


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
