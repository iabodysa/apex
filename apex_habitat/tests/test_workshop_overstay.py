# Copyright (c) 2026, AFMCO and contributors
"""Tests for workshop_overstay_watch: a maintenance Vehicle Stop left open past
the cutoff raises a Maintenance Overdue Operations Alert; a recent one does not.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex_habitat.salis.tasks import _overstay_stops, workshop_overstay_watch

ALERT = {"alert_type": "Maintenance Overdue", "status": "Open"}


class TestWorkshopOverstay(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def _vehicle_with_maintenance_stop(self, stop_days_ago, return_date=None):
        # [#atg6pq]
        plate = "WO " + self._testMethodName
        vehicle = frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
        ).insert(ignore_permissions=True).name
        self.stop = frappe.get_doc(
            {
                "doctype": "Vehicle Stop",
                "vehicle": vehicle,
                "stop_reason": "Maintenance",
                "stop_date": add_days(today(), -stop_days_ago),
            }
        ).insert(ignore_permissions=True)
        self.stop.submit()  # [#ij3jpf]
        # submit leaves return_date NULL (vehicle now Stopped); a closed stop sets it.
        if return_date:
            frappe.db.set_value("Vehicle Stop", self.stop.name, "return_date", return_date)
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
        # [#qsakev]
        frappe.db.set_value("Salis Vehicle", vehicle, "status", "Active")
        workshop_overstay_watch()
        self.assertFalse(
            frappe.db.exists("Operations Alert", {"vehicle": vehicle, **ALERT}),
            "an Active (recovered) vehicle must NOT raise an overstay alert",
        )

    def test_overstay_stops_counts_null_return_date(self):
        # A freshly-submitted overstaying stop has return_date NULL; the open-stop
        # filter must count it. Direct unit on _overstay_stops (no alert dedupe).
        self._vehicle_with_maintenance_stop(20)
        self.assertIsNone(
            frappe.db.get_value("Vehicle Stop", self.stop.name, "return_date"),
            "guard: the submitted maintenance stop must have a NULL return_date",
        )
        names = {r.name for r in _overstay_stops()}
        self.assertIn(
            self.stop.name, names,
            "an open maintenance stop with NULL return_date must be counted as overstaying",
        )

    def test_overstay_stops_excludes_closed_return_date(self):
        # Non-vacuous guard: a stop whose return_date is set (workshop exit) is
        # closed and must NOT be counted, even when stop_date is past the cutoff.
        self._vehicle_with_maintenance_stop(20, return_date=add_days(today(), -1))
        names = {r.name for r in _overstay_stops()}
        self.assertNotIn(
            self.stop.name, names,
            "a closed maintenance stop (return_date set) must NOT be counted as overstaying",
        )
