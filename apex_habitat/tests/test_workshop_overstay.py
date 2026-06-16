"""Tests for workshop_overstay_watch: a maintenance Vehicle Stop left open past
the cutoff raises a Maintenance Overdue Operations Alert; a recent one does not.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex_habitat.salis.tasks import workshop_overstay_watch

ALERT = {"alert_type": "Maintenance Overdue", "status": "Open"}


class TestWorkshopOverstay(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def _vehicle_with_maintenance_stop(self, stop_days_ago):
        # [#5wbd96]
        plate = "WO " + self._testMethodName
        vehicle = frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
        ).insert(ignore_permissions=True).name
        stop = frappe.get_doc(
            {
                "doctype": "Vehicle Stop",
                "vehicle": vehicle,
                "stop_reason": "Maintenance",
                "stop_date": add_days(today(), -stop_days_ago),
            }
        ).insert(ignore_permissions=True)
        stop.submit()  # [#ij3jpf]
        frappe.db.delete("Operations Alert", {"vehicle": vehicle, "alert_type": "Maintenance Overdue"})
        return vehicle

    def test_overstay_raises_alert(self):
        vehicle = self._vehicle_with_maintenance_stop(20)  # [#385kmo]
        workshop_overstay_watch()
        self.assertTrue(
            frappe.db.exists("Operations Alert", {"vehicle": vehicle, **ALERT}),
            "a maintenance stop open 20 days must raise a Maintenance Overdue alert",
        )

    def test_recent_stop_no_alert(self):
        vehicle = self._vehicle_with_maintenance_stop(2)  # [#kgy7up]
        workshop_overstay_watch()
        self.assertFalse(
            frappe.db.exists("Operations Alert", {"vehicle": vehicle, **ALERT}),
            "a recent maintenance stop must NOT raise an overstay alert",
        )

    def test_recovered_vehicle_no_alert(self):
        vehicle = self._vehicle_with_maintenance_stop(20)
        # [#tdk54g]
        frappe.db.set_value("Salis Vehicle", vehicle, "status", "Active")
        workshop_overstay_watch()
        self.assertFalse(
            frappe.db.exists("Operations Alert", {"vehicle": vehicle, **ALERT}),
            "an Active (recovered) vehicle must NOT raise an overstay alert",
        )
