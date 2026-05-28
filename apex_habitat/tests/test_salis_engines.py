"""Idempotency tests for the Salis background engines: re-running a daily/weekly
job must never double-post its ledger/snapshot rows."""

import unittest

import frappe

from apex_habitat.salis.rental_engine import daily_rental_accrual
from apex_habitat.salis.utilisation_engine import weekly_vehicle_utilisation_snapshot


class TestRentalAccrualIdempotency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.office = frappe.db.get_value("Rental Office", {"office_name": "Eng Test Office"}, "name")
        if not cls.office:
            cls.office = frappe.get_doc({"doctype": "Rental Office",
                                         "office_name": "Eng Test Office",
                                         "status": "Active"}).insert(ignore_permissions=True).name
        cls.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": "RENT ENG 1"}, "name")
        if not cls.vehicle:
            cls.vehicle = frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": "RENT ENG 1",
                                          "ownership": "Rented", "status": "Active"}).insert(
                ignore_permissions=True).name
        if not frappe.db.exists("Rental Vehicle Movement",
                                {"vehicle": cls.vehicle, "movement_type": "Receipt", "docstatus": 1}):
            m = frappe.get_doc({"doctype": "Rental Vehicle Movement", "movement_type": "Receipt",
                                "vehicle": cls.vehicle, "rental_office": cls.office,
                                "movement_date": frappe.utils.today(), "daily_rate": 100}).insert(
                ignore_permissions=True)
            m.submit()
        frappe.db.commit()

    def test_accrual_is_idempotent(self):
        today = frappe.utils.today()
        frappe.db.delete("Rental Accrual Ledger", {"vehicle": self.vehicle, "accrual_date": today})
        frappe.db.commit()
        daily_rental_accrual()
        frappe.db.commit()
        first = frappe.db.count("Rental Accrual Ledger", {"vehicle": self.vehicle, "accrual_date": today})
        daily_rental_accrual()
        frappe.db.commit()
        second = frappe.db.count("Rental Accrual Ledger", {"vehicle": self.vehicle, "accrual_date": today})
        self.assertEqual(first, 1)
        self.assertEqual(second, 1)


class TestUtilisationSnapshotIdempotency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": "UTIL ENG 1"}, "name")
        if not cls.vehicle:
            cls.vehicle = frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": "UTIL ENG 1",
                                          "status": "Active"}).insert(ignore_permissions=True).name
        frappe.db.commit()

    def test_snapshot_is_idempotent(self):
        today = frappe.utils.today()
        frappe.db.delete("Vehicle Utilisation Snapshot", {"vehicle": self.vehicle, "snapshot_date": today})
        frappe.db.commit()
        weekly_vehicle_utilisation_snapshot()
        frappe.db.commit()
        first = frappe.db.count("Vehicle Utilisation Snapshot", {"vehicle": self.vehicle, "snapshot_date": today})
        weekly_vehicle_utilisation_snapshot()
        frappe.db.commit()
        second = frappe.db.count("Vehicle Utilisation Snapshot", {"vehicle": self.vehicle, "snapshot_date": today})
        self.assertEqual(first, 1)
        self.assertEqual(second, 1)
