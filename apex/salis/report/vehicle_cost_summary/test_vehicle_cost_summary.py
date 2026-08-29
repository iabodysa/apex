# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_datetime

from apex.salis.report.vehicle_cost_summary.vehicle_cost_summary import execute
from apex.tests.factories import make_rental_office, make_vehicle

WINDOW = {"from_date": "2026-04-01", "to_date": "2026-04-10"}


class TestVehicleCostSummary(FrappeTestCase):
    def setUp(self):
        self.vehicle = make_vehicle("_T-VCS 0001")

    def _fuel(self, litres, amount, **fields):
        data = {
            "doctype": "Fuel Consumption Ledger",
            "vehicle": self.vehicle,
            "period_month": "2026-04",
            "litres": litres,
            "amount": amount,
            "logged_at": get_datetime("2026-04-05 09:00:00"),
            "source_type": "Fuel Request",
            "source_doctype": "Fuel Request",
            "source_name": "_T-VCS-" + frappe.generate_hash(length=8),
        }
        data.update(fields)
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete("Fuel Consumption Ledger", {"name": name})
        )
        return doc

    def _rental(self, amount):
        doc = frappe.get_doc(
            {
                "doctype": "Rental Accrual Ledger",
                "vehicle": self.vehicle,
                "rental_office": make_rental_office("_T-VCS Office"),
                "accrual_date": "2026-04-06",
                "daily_rate": amount,
                "amount": amount,
                "source_doctype": "Rental Vehicle Movement",
                "source_name": "_T-VCS-" + frappe.generate_hash(length=8),
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete("Rental Accrual Ledger", {"name": name})
        )
        return doc

    def _row(self):
        rows = execute(dict(WINDOW, vehicle=self.vehicle))[1]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_fuel_and_rental_add_up_over_the_ten_day_window(self):
        self._fuel(40.0, 92.0)
        self._rental(50.0)

        row = self._row()
        self.assertEqual(row["fuel_litres"], 40.0)
        self.assertEqual(row["fuel_cost"], 92.0)
        self.assertEqual(row["rental_cost"], 50.0)
        self.assertEqual(row["net_cost"], 142.0)
        self.assertEqual(row["cost_per_day"], 14.2)

    def test_a_reversed_fuel_row_nets_the_original_out(self):
        original = self._fuel(40.0, 92.0)
        self._fuel(-40.0, -92.0, source_name=original.source_name, reversal_of=original.name)

        row = self._row()
        self.assertEqual(row["fuel_litres"], 0.0)
        self.assertEqual(row["fuel_cost"], 0.0)
        self.assertEqual(row["net_cost"], 0.0)

    def test_a_ledger_row_outside_the_window_is_left_out(self):
        self._fuel(40.0, 92.0, logged_at=get_datetime("2026-05-01 09:00:00"))

        row = self._row()
        self.assertEqual(row["fuel_cost"], 0.0)
