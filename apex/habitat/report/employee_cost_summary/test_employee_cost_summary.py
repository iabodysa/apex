# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.report.employee_cost_summary.employee_cost_summary import execute

test_dependencies = ["Building", "Employee", "Custody Article"]
test_ignore = ["Project"]

EMPLOYEE = "_T-Employee-00001"
BUILDING = "_Test Building"
WINDOW = {"from_date": "2026-03-01", "to_date": "2026-03-31", "employee": EMPLOYEE}


class TestEmployeeCostSummary(FrappeTestCase):
    def _ledger_row(self, **fields):
        data = {
            "doctype": "Accommodation Ledger",
            "posting_date": "2026-03-01",
            "ledger_type": "Rent",
            "posting_mode": "Operational Memo",
            "building": BUILDING,
            "employee": EMPLOYEE,
            "employee_daily_share": 100.0,
            "source_doctype": "Housing Assignment",
            "source_name": "_T-ECS-" + frappe.generate_hash(length=8),
        }
        data.update(fields)
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=doc.name: frappe.db.delete("Accommodation Ledger", {"name": name})
        )
        return doc

    def _row(self):
        rows = execute(dict(WINDOW))[1]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_a_reversed_night_leaves_no_cost_and_no_housed_day(self):
        original = self._ledger_row(posting_date="2026-03-02")
        self._ledger_row(
            posting_date="2026-03-02",
            source_name=original.source_name,
            employee_daily_share=-100.0,
            reversal_of=original.name,
        )
        self._ledger_row(posting_date="2026-03-03")

        row = self._row()
        self.assertEqual(row["accommodation_cost"], 100.0)
        self.assertEqual(row["days_housed"], 1)
        self.assertEqual(row["cost_per_day"], 100.0)

    def test_custody_issued_in_the_window_adds_to_the_net_cost(self):
        self._ledger_row(posting_date="2026-03-04")
        stock = frappe.get_doc(
            {
                "doctype": "Accommodation Stock Ledger",
                "posting_date": "2026-03-05",
                "building": BUILDING,
                "employee": EMPLOYEE,
                "item_type": "Custody Article",
                "item": frappe.get_all(
                    "Custody Article", filters={"article_name": "_Test Blanket"}, pluck="name"
                )[0],
                "item_name": "_Test Blanket",
                "signed_qty": 2.0,
                "unit_cost": 25.0,
                "voucher_type": "Custody Issue",
                "voucher_no": "_T-ECS-" + frappe.generate_hash(length=8),
            }
        )
        stock.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=stock.name: frappe.db.delete("Accommodation Stock Ledger", {"name": name})
        )

        row = self._row()
        self.assertEqual(row["custody_cost"], 50.0)
        self.assertEqual(row["net_cost"], 150.0)

    def test_a_recovery_from_the_employee_reduces_the_net_cost(self):
        self._ledger_row(posting_date="2026-03-04")
        recovery = frappe.get_doc(
            {
                "doctype": "Movement Cost Recovery",
                "recovery_type": "Vehicle Damage",
                "employee": EMPLOYEE,
                "request_date": "2026-03-05",
                "status": "Open",
                "acknowledgement_received": 1,
                "basis_evidence": "/files/_t_ecs_evidence.pdf",
                "amount": 40.0,
            }
        )
        recovery.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            lambda name=recovery.name: frappe.db.delete("Movement Cost Recovery", {"name": name})
        )
        frappe.db.set_value(
            "Movement Cost Recovery", recovery.name, "status", "Recovered", update_modified=False
        )
        recovery.reload()
        recovery.submit()

        row = self._row()
        self.assertEqual(row["recovered"], 40.0)
        self.assertEqual(row["net_cost"], 60.0)
