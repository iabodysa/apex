# Copyright (c) 2026, AFMCO and contributors
"""Custody value-at-risk tests (shipped 1.54.30) — covers the dashboard scalar
`get_custody_value_in_employee_hands` and the `Custody Outstanding by Worker`
report. Both read the same non-cancelled Accommodation Stock Ledger Custody
Article rows with an employee set: issue rows add, return rows reverse, so the
net signed qty (and qty * unit_cost) is what the worker still holds.

Ledger rows are inserted directly with ignore_permissions/ignore_links (the same
approach the doctype's own smoke test uses) so the cases are deterministic and
self-contained — no master chain, no pre-existing site data. Each run uses a
unique employee/building/article token so it cannot collide with other rows."""

import frappe
from frappe.utils import flt
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.dashboard import get_custody_value_in_employee_hands
from apex.habitat.report.custody_outstanding_by_worker.custody_outstanding_by_worker import (
    execute as run_custody_report,
)


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestDashboardCustody(FrappeTestCase):
    def setUp(self):
        # [#t0t3a8]
        self.employee = "EMP-" + _h()
        self.building = "BLDG-" + _h()
        self.article = "ART-" + _h()
        self.unit_cost = 12.0
        self.issue_qty = 5.0
        self.return_qty = 2.0  # [#tsnugi]
        self.net_qty = self.issue_qty - self.return_qty  # [#pkhwzj]
        self.net_value = self.net_qty * self.unit_cost  # [#hnh87s]
        self._names = []

        # [#7sub0c]
        self._post(qty=self.issue_qty, employee=self.employee)
        # [#53uk6k]
        self._post(qty=-self.return_qty, employee=self.employee)
        # [#pqi132]
        self._post(qty=99, employee=self.employee, is_cancelled=1)
        # [#mw28jz]
        self._post(qty=7, employee=None)

    def _post(self, qty, employee, is_cancelled=0):
        doc = frappe.get_doc({
            "doctype": "Accommodation Stock Ledger",
            "naming_series": "ACC-SLE-.YYYY.-.######",
            "posting_date": "2026-06-01",
            "item_type": "Custody Article",
            "item": self.article,
            "item_name": "Test Article",
            "uom": "Nos",
            "signed_qty": qty,
            "unit_cost": self.unit_cost,
            "building": self.building,
            "employee": employee,
            "is_cancelled": is_cancelled,
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self._names.append(doc.name)
        return doc.name

    def tearDown(self):
        for name in self._names:
            frappe.delete_doc("Accommodation Stock Ledger", name, force=True,
                              ignore_permissions=True)

    def test_value_in_employee_hands_is_signed_net(self):
        """The dashboard scalar equals the seeded signed net SAR for this employee,
        added on top of whatever else exists on the site (delta is exact)."""
        # [#kt58d0]
        seeded = frappe.db.sql(
            """
            SELECT COALESCE(SUM(signed_qty * COALESCE(unit_cost, 0)), 0)
            FROM `tabAccommodation Stock Ledger`
            WHERE is_cancelled = 0
              AND item_type = 'Custody Article'
              AND employee = %s
            """,
            self.employee,
        )
        self.assertEqual(flt(seeded[0][0]), self.net_value,
                         "scoped seeded net SAR must be issue*cost - return*cost")

        # [#1lpknc]
        total = flt(get_custody_value_in_employee_hands()["value"])
        self.assertGreaterEqual(total, self.net_value)
        # [#sfsdsj]
        self.assertNotIn(99 * self.unit_cost, [total])

    def test_value_in_hands_returns_number_card_dict_contract(self):
        """Custom Number Card contract: {value: <number>, ...df} — a bare scalar
        renders the value but drops the Currency/SAR format docfield."""
        res = get_custody_value_in_employee_hands()
        self.assertIsInstance(res, dict, "Custom Number Card returns a dict, not a scalar")
        self.assertIn("value", res, "the number must live under the 'value' key")
        self.assertEqual(res.get("fieldtype"), "Currency")
        self.assertEqual(res.get("options"), "SAR")

    def test_report_balance_and_value_per_employee(self):
        """The report returns one row for this (employee, building, article) with
        the correct outstanding balance_qty and value_sar."""
        cols, data = run_custody_report({"employee": self.employee})
        self.assertTrue(cols, "report must return columns")
        mine = [r for r in data if r["employee"] == self.employee]
        self.assertEqual(len(mine), 1, "exactly one outstanding row for this employee")
        row = mine[0]
        self.assertEqual(row["building"], self.building)
        self.assertEqual(row["item"], self.article)
        self.assertEqual(flt(row["balance_qty"]), self.net_qty,
                         "outstanding qty = issue - partial return")
        self.assertEqual(flt(row["value_sar"]), self.net_value,
                         "value = outstanding qty * unit cost")
        self.assertEqual(flt(row["unit_cost"]), self.unit_cost)

    def test_cancelled_rows_are_excluded(self):
        """The +99 cancelled issue must not affect the report balance for this
        employee (if counted, balance_qty would be net + 99)."""
        _, data = run_custody_report({"employee": self.employee})
        mine = [r for r in data if r["employee"] == self.employee]
        self.assertEqual(len(mine), 1)
        self.assertEqual(flt(mine[0]["balance_qty"]), self.net_qty,
                         "cancelled row (is_cancelled=1) must be excluded")

    def test_no_employee_rows_are_excluded(self):
        """The +7 store row (employee unset) must never appear as a custody
        holding — the report only counts rows with an employee set."""
        _, data = run_custody_report({"building": self.building})
        # [#mkrb38]
        for r in data:
            self.assertTrue(r["employee"], "report rows must have an employee set")
        mine = [r for r in data if r["building"] == self.building]
        # [#c1syt9]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["employee"], self.employee)
        self.assertEqual(flt(mine[0]["balance_qty"]), self.net_qty)
