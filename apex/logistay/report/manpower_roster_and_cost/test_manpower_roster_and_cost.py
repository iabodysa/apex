# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.logistay.report.manpower_roster_and_cost.manpower_roster_and_cost import execute


class TestManpowerRosterAndCost(FrappeTestCase):
    def _freelancer(self, salary, ends_in_days):
        doc = frappe.get_doc(
            {
                "doctype": "Freelancer",
                "full_name": "_T-MRC " + frappe.generate_hash(length=6),
                "national_id_or_iqama": frappe.generate_hash(length=10),
                "status": "Active",
                "contract_start_date": today(),
                "contract_end_date": add_days(today(), ends_in_days),
                "monthly_salary": salary,
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(lambda name=doc.name: frappe.db.delete("Freelancer", {"name": name}))
        return doc

    def _rows(self, filters):
        return execute(filters)[1]

    def _mine(self, rows, worker):
        return next(row for row in rows if row["worker"] == worker)

    def test_a_freelancer_carries_a_monthly_cost_and_its_days_to_expiry(self):
        freelancer = self._freelancer(4000.0, 20)

        row = self._mine(self._rows({"within_days": 0}), freelancer.name)
        self.assertEqual(row["worker_type"], "Freelancer")
        self.assertEqual(row["monthly_cost"], 4000.0)
        self.assertEqual(row["days_to_expiry"], 20)

    def test_the_horizon_filter_hides_a_contract_that_ends_after_it(self):
        near = self._freelancer(1000.0, 10)
        far = self._freelancer(1000.0, 400)

        workers = {row["worker"] for row in self._rows({"within_days": 30})}
        self.assertIn(near.name, workers)
        self.assertNotIn(far.name, workers)

    def test_the_worker_type_filter_keeps_temporary_workers_out(self):
        freelancer = self._freelancer(1000.0, 10)

        rows = self._rows({"worker_type": "Freelancer", "within_days": 0})
        self.assertIn(freelancer.name, {row["worker"] for row in rows})
        self.assertEqual({row["worker_type"] for row in rows}, {"Freelancer"})
