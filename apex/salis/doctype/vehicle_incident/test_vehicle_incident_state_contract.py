from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.salis.api import fleet_os
from apex.salis.doctype.vehicle_incident import vehicle_incident


def _raising_frappe() -> MagicMock:
    fake = MagicMock()
    fake.PermissionError = frappe.PermissionError

    def throw(message, exc=None, **_kwargs):
        raise (exc or frappe.ValidationError)(message)

    fake.throw.side_effect = throw
    return fake


def _call(endpoint, *args, **kwargs):
    return getattr(endpoint, "__wrapped__", endpoint)(*args, **kwargs)


class TestVehicleIncidentLifecycle(TestCase):
    def test_new_incident_is_open_and_direct_status_edit_is_refused(self):
        fake = _raising_frappe()
        new_doc = MagicMock(status="Closed")
        new_doc.is_new.return_value = True

        existing = MagicMock(status="Closed")
        existing.is_new.return_value = False
        existing.has_value_changed.return_value = True

        with (
            patch.object(vehicle_incident, "frappe", fake),
            patch.object(vehicle_incident, "_", side_effect=lambda message: message),
        ):
            vehicle_incident.VehicleIncident._guard_status(new_doc)
            with self.assertRaises(frappe.PermissionError):
                vehicle_incident.VehicleIncident._guard_status(existing)

        self.assertEqual(new_doc.status, "Open")

    def test_submit_and_cancel_use_canonical_statuses(self):
        submitted = MagicMock(incident_type="Accident")
        cancelled = MagicMock(incident_type="Accident")

        vehicle_incident.VehicleIncident.on_submit(submitted)
        vehicle_incident.VehicleIncident.on_cancel(cancelled)

        submitted.db_set.assert_called_once_with("status", "Under Review")
        cancelled.db_set.assert_called_once_with("status", "Closed")

    def test_close_requires_write_permission_and_resolution(self):
        doc = MagicMock(docstatus=1, status="Under Review")
        doc.name = "VI-1"
        doc.vehicle = "VEH-1"
        doc.check_permission.side_effect = frappe.PermissionError("denied")
        fake = _raising_frappe()
        fake.get_doc.return_value = doc

        with (
            patch.object(vehicle_incident, "frappe", fake),
            patch.object(vehicle_incident, "_", side_effect=lambda message: message),
        ):
            with self.assertRaises(frappe.ValidationError):
                _call(vehicle_incident.close_incident, "VI-1", "  ")
            with self.assertRaises(frappe.PermissionError):
                _call(vehicle_incident.close_incident, "VI-1", "Repair completed")

        doc.db_set.assert_not_called()

    def test_close_transitions_under_review_and_writes_timeline(self):
        doc = MagicMock(docstatus=1, status="Under Review")
        doc.name = "VI-1"
        doc.vehicle = "VEH-1"
        fake = _raising_frappe()
        fake.get_doc.return_value = doc

        with (
            patch.object(vehicle_incident, "frappe", fake),
            patch.object(vehicle_incident, "_", side_effect=lambda message: message),
            patch.object(vehicle_incident, "add_timeline_note") as add_note,
        ):
            result = _call(vehicle_incident.close_incident, "VI-1", "Repair completed")

        fake.get_doc.assert_called_once_with(
            "Vehicle Incident", "VI-1", for_update=True
        )
        doc.db_set.assert_called_once_with("status", "Closed")
        self.assertIn("Repair completed", doc.add_comment.call_args.args[1])
        add_note.assert_called_once()
        self.assertEqual(result, {"name": "VI-1", "status": "Closed"})

    def test_fleet_recovery_reuses_incident_close_transition(self):
        incident = frappe._dict(
            name="VI-1",
            previous_driver=None,
            previous_status="Active",
        )
        fake = MagicMock()
        fake.db.get_value.side_effect = [incident]

        with (
            patch.object(fleet_os, "frappe", fake),
            patch.object(fleet_os, "_", side_effect=lambda message: message),
            patch.object(fleet_os, "_resolve_plate", return_value="VEH-1"),
            patch.object(fleet_os, "lock_vehicle"),
            patch.object(fleet_os, "_close_open_suspension"),
            patch.object(fleet_os, "_publish_fleet_update"),
            patch.object(
                fleet_os, "close_incident_internal", create=True
            ) as close_incident,
        ):
            result = _call(fleet_os.recover, "1234")

        close_incident.assert_called_once_with(
            "VI-1",
            "Vehicle recovered through Fleet OS.",
            check_permission=False,
        )
        self.assertEqual(result, {"ok": True, "incident": "VI-1"})


class TestVehicleIncidentMetadata(TestCase):
    def test_status_is_read_only_and_cancelled_is_not_a_parallel_state(self):
        metadata = json.loads(
            Path(__file__)
            .with_name("vehicle_incident.json")
            .read_text(encoding="utf-8")
        )
        status = next(
            field for field in metadata["fields"] if field["fieldname"] == "status"
        )
        self.assertEqual(
            status["options"].splitlines(), ["Open", "Under Review", "Closed"]
        )
        self.assertTrue(status["read_only"])
        self.assertNotIn("Cancelled", {state["title"] for state in metadata["states"]})
