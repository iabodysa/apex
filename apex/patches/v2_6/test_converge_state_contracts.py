from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

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
