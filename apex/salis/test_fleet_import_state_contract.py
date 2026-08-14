from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.salis import fleet_import


def _only_driver_rows(rows):
    def read(_csv_dir, name):
        return rows if name == "salis_driver.csv" else []

    return read


def _raising_frappe():
    fake = MagicMock()
    fake._.side_effect = lambda message: message

    def throw(message):
        raise frappe.ValidationError(message)

    fake.throw.side_effect = throw
    return fake


class TestFleetImportDriverContract(TestCase):
    def _run(self, fake, rows):
        with (
            patch.object(fleet_import, "frappe", fake),
            patch.object(fleet_import, "_read", side_effect=_only_driver_rows(rows)),
        ):
            return fleet_import.run("/tmp/fleet-import-contract")

    def test_existing_driver_keeps_lifecycle_status_and_updates_master_data(self):
        driver = SimpleNamespace(
            full_name="Old Name",
            phone=None,
            project=None,
            status="Stopped",
            save=MagicMock(),
        )
        fake = MagicMock()
        fake.db.get_value.return_value = "DRV-1"
        fake.get_doc.return_value = driver
        result = self._run(fake, [{
            "driver_id": "EMP-1", "full_name": "Updated Name",
            "phone": "0500000000", "status": "Active",
        }])

        self.assertEqual(driver.full_name, "Updated Name")
        self.assertEqual(driver.phone, "0500000000")
        self.assertEqual(driver.status, "Stopped")
        driver.save.assert_called_once_with(ignore_permissions=True)
        self.assertEqual(result["drivers"], 1)

    def test_new_driver_relies_on_document_default_for_lifecycle_status(self):
        inserted = SimpleNamespace(name="DRV-NEW")
        document = MagicMock()
        document.insert.return_value = inserted
        fake = MagicMock()
        fake.db.get_value.return_value = None
        fake.get_doc.return_value = document
        result = self._run(fake, [{
            "driver_id": "EMP-NEW", "full_name": "New Driver", "status": "",
        }])

        payload = fake.get_doc.call_args.args[0]
        self.assertNotIn("status", payload)
        self.assertEqual(result["drivers"], 1)

    def test_non_active_imported_status_fails_with_driver_context(self):
        fake = _raising_frappe()
        rows = [{"driver_id": "EMP-STOPPED", "status": "Stopped"}]

        with self.assertRaisesRegex(frappe.ValidationError, "EMP-STOPPED.*Stopped"):
            self._run(fake, rows)

        fake.db.get_value.assert_not_called()

    def test_driver_validation_failure_is_not_silently_dropped(self):
        driver = SimpleNamespace(
            full_name="Old Name",
            phone=None,
            project=None,
            status="Stopped",
            save=MagicMock(side_effect=frappe.ValidationError("invalid driver")),
        )
        fake = MagicMock()
        fake.db.get_value.return_value = "DRV-1"
        fake.get_doc.return_value = driver
        rows = [{"driver_id": "EMP-1", "full_name": "Driver"}]

        with self.assertRaisesRegex(frappe.ValidationError, "invalid driver"):
            self._run(fake, rows)

    def test_driver_row_without_natural_key_is_not_silently_dropped(self):
        fake = _raising_frappe()
        rows = [{"driver_id": "", "full_name": "Unidentified Driver"}]

        with self.assertRaisesRegex(frappe.ValidationError, "Driver ID is required"):
            self._run(fake, rows)
