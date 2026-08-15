from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import call, patch

from apex.salis.doctype.driver_clearance import driver_clearance


class TestDriverClearance(TestCase):
    @patch.object(driver_clearance, "add_timeline_note")
    @patch.object(driver_clearance, "set_current_driver")
    @patch.object(driver_clearance, "lock_driver")
    @patch.object(driver_clearance, "lock_vehicle", create=True)
    @patch.object(driver_clearance, "frappe")
    def test_release_clears_both_sides_of_matching_vehicle_link(
        self, frappe, lock_vehicle, _lock_driver, set_current_driver, _timeline
    ):
        """The vehicle half goes through ``salis.utils.set_current_driver``, which clears
        ``current_driver_user`` alongside ``current_driver``. Leaving the user mirror
        behind would keep mailing the cleared rider about that vehicle."""
        doc = SimpleNamespace(
            driver="DRV-1",
            name="CLR-1",
            clearance_reason="Termination",
        )
        frappe.db.exists.return_value = True
        frappe.db.get_value.side_effect = ["VEH-1", "DRV-1"]

        driver_clearance.DriverClearance._release_driver(doc)

        lock_vehicle.assert_called_once_with("VEH-1")
        set_current_driver.assert_called_once_with("VEH-1", None)
        self.assertIn(
            call(
                "Salis Driver",
                "DRV-1",
                {"status": "Released", "current_vehicle": None},
            ),
            frappe.db.set_value.call_args_list,
        )

    @patch.object(driver_clearance, "add_timeline_note")
    @patch.object(driver_clearance, "lock_driver")
    @patch.object(driver_clearance, "lock_vehicle", create=True)
    @patch.object(driver_clearance, "frappe")
    def test_release_does_not_unlink_vehicle_reassigned_to_another_driver(
        self, frappe, lock_vehicle, _lock_driver, _timeline
    ):
        doc = SimpleNamespace(
            driver="DRV-1",
            name="CLR-1",
            clearance_reason="Termination",
        )
        frappe.db.exists.return_value = True
        frappe.db.get_value.side_effect = ["VEH-1", "DRV-2"]

        driver_clearance.DriverClearance._release_driver(doc)

        lock_vehicle.assert_called_once_with("VEH-1")
        self.assertNotIn(
            call("Salis Vehicle", "VEH-1", "current_driver", None),
            frappe.db.set_value.call_args_list,
        )
        self.assertIn(
            call(
                "Salis Driver",
                "DRV-1",
                {"status": "Released", "current_vehicle": None},
            ),
            frappe.db.set_value.call_args_list,
        )
