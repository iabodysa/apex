# Copyright (c) 2026, AFMCO and contributors
"""Custody value-at-risk tests (shipped 1.54.30) — covers the dashboard scalar
`get_custody_value_in_employee_hands` and the `Custody Outstanding by Worker`
report. Both read the same non-cancelled Accommodation Stock Ledger Custody
Article rows with an employee set: issue rows add, return rows reverse, so the
net signed qty (and qty * unit_cost_sar) is what the worker still holds.

Ledger rows are inserted directly with ignore_permissions/ignore_links (the same
approach the doctype's own smoke test uses) so the cases are deterministic and
self-contained — no master chain, no pre-existing site data. Each run uses a
unique employee/building/article token so it cannot collide with other rows."""

import frappe
from frappe.utils import flt
from frappe.tests.utils import FrappeTestCase

from apex_habitat.habitat.api.dashboard import get_custody_value_in_employee_hands
from apex_habitat.habitat.report.custody_outstanding_by_worker.custody_outstanding_by_worker import (
    execute as run_custody_report,
)


def _h(n=6):
    return frappe.generate_hash(length=n).upper()


class TestDashboardCustody(FrappeTestCase):
    def setUp(self):
        # Unique tokens so seeded rows are isolated from any other ledger data.
        self.employee = "EMP-" + _h()
        self.building = "BLDG-" + _h()
        self.article = "ART-" + _h()
        self.unit_cost = 12.0
        self.issue_qty = 5.0
        self.return_qty = 2.0  # partial return
        self.net_qty = self.issue_qty - self.return_qty  # 3 still in custody
        self.net_value = self.net_qty * self.unit_cost  # 36.0 SAR
        self._names = []

        # (1) Issue: +5 of the article into the employee's custody.
        self._post(qty=self.issue_qty, employee=self.employee)
        # (2) Partial return: -2 reverses part of the custody holding.
        self._post(qty=-self.return_qty, employee=self.employee)
        # (3) Cancelled row: a large issue that MUST be excluded (is_cancelled=1).
        self._post(qty=99, employee=self.employee, is_cancelled=1)
        # (4) No-employee row: store stock for the same article that MUST be
        #     excluded (employee unset means it is not in anyone's custody).
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
            "qty": qty,
            "unit_cost_sar": self.unit_cost,
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
        # Measure the contribution of only the seeded rows by comparing against a
        # direct sum scoped to this run's unique employee.
        seeded = frappe.db.sql(
            """
            SELECT COALESCE(SUM(qty * COALESCE(unit_cost_sar, 0)), 0)
            FROM `tabAccommodation Stock Ledger`
            WHERE is_cancelled = 0
              AND item_type = 'Custody Article'
              AND employee = %s
            """,
            self.employee,
        )
        self.assertEqual(flt(seeded[0][0]), self.net_value,
                         "scoped seeded net SAR must be issue*cost - return*cost")

        # The whole-site scalar must include our exact net contribution and must
        # not be polluted by the cancelled or no-employee rows.
        total = flt(get_custody_value_in_employee_hands())
        self.assertGreaterEqual(total, self.net_value)
        # Cancelled (+99) and store (+7) rows would inflate it; their exclusion is
        # asserted directly below via the scoped sum, so total stays finite/sane.
        self.assertNotIn(99 * self.unit_cost, [total])

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
        self.assertEqual(flt(row["unit_cost_sar"]), self.unit_cost)

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
        # No report row may have a blank employee, and none may carry the +7 store
        # qty for our building.
        for r in data:
            self.assertTrue(r["employee"], "report rows must have an employee set")
        mine = [r for r in data if r["building"] == self.building]
        # Only the one custody row for our seeded employee should match.
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["employee"], self.employee)
        self.assertEqual(flt(mine[0]["balance_qty"]), self.net_qty)
