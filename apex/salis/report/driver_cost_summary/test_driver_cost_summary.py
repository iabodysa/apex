# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_datetime

from apex.salis.report.driver_cost_summary.driver_cost_summary import execute
from apex.tests.factories import make_test_driver, make_vehicle

WINDOW = {"from_date": "2026-04-01", "to_date": "2026-04-10"}


class TestDriverCostSummary(FrappeTestCase):
    def setUp(self):
        self.driver = make_test_driver()
        self.vehicle = make_vehicle("_T-DCS 0001")

    def _fuel(self, litres, amount):
        doc = frappe.get_doc(
            {
                "doctype": "Fuel Consumption Ledger",
                "vehicle": self.vehicle,
                "driver": self.driver,
                "period_month": "2026-04",
                "litres": litres,
                "amount": amount,
                "logged_at": get_datetime("2026-04-05 09:00:00"),
                "source_type": "Fuel Request",
                "source_doctype": "Fuel Request",
                "source_name": "_T-DCS-" + frappe.generate_hash(length=8),
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete("Fuel Consumption Ledger", {"name": name})
        )
        return doc

    def _attendance(self, date, status="Present", hours=8.0):
        doc = frappe.get_doc(
            {
                "doctype": "Driver Attendance",
                "driver": self.driver,
                "attendance_date": date,
                "status": status,
                "worked_hours": hours,
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete("Driver Attendance", {"name": name})
        )
        return doc

    def _row(self):
        rows = execute(dict(WINDOW, driver=self.driver))[1]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_fuel_is_charged_per_present_day(self):
        self._fuel(40.0, 100.0)
        self._attendance("2026-04-05")
        self._attendance("2026-04-06")

        row = self._row()
        self.assertEqual(row["present_days"], 2)
        self.assertEqual(row["fuel_cost"], 100.0)
        self.assertEqual(row["net_cost"], 100.0)
        self.assertEqual(row["cost_per_present_day"], 50.0)

    def test_an_absent_day_is_not_a_present_day(self):
        self._fuel(40.0, 100.0)
        self._attendance("2026-04-05")
        self._attendance("2026-04-06", status="Absent", hours=0.0)

        row = self._row()
        self.assertEqual(row["present_days"], 1)
        self.assertEqual(row["cost_per_present_day"], 100.0)
