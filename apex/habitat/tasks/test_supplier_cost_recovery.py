# Copyright (c) 2026, afmcoltd
"""Supplier accommodation cost recovery: the daily allocation carries billed_to_supplier down to
the ledger, the report aggregates the month with the markup applied, and the dispatcher hands each
building to its own long-queue job.

The building, its rooms, its beds, the employee and the supplier all come from ``test_records.json``
— Supplier from ERPNext's own. The only thing arranged here is the building's annual rent, which is
the number the daily share is computed from, and it is handed straight back. The previous form of
this file built a Company, a Supplier, a Site, a Building, a Room, a Bed and an Employee in
``setUp``, per test method.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, getdate

from apex.habitat.report.supplier_cost_recovery.supplier_cost_recovery import execute
from apex.habitat.tasks import (
    allocate_building_accommodation_cost,
    daily_accommodation_cost_allocation,
)

# Project is deliberately NOT a dependency. ERPNext's Project fixture is not idempotent — its
# autoname mints a new name while project_name carries a unique index, so a second build attempt
# collides instead of being skipped.
test_dependencies = ["Bed", "Employee", "Supplier"]

BUILDING = "_Test Building"
ROOM = "_T-101"
BED = "_T-101-A"
SUPPLIER = "_Test Supplier"
ANNUAL_RENT = 36500


class TestSupplierCostRecovery(FrappeTestCase):
    def setUp(self):
        # FrappeTestCase rolls the database back once per CLASS, not once per method —
        # frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup — so the assignment
        # one case houses would still hold the fixture bed when the next case tries, and the rent
        # it set would still be on the building. A savepoint hands both back.
        frappe.db.savepoint("apex_supplier_recovery_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_supplier_recovery_case")
        self.addCleanup(frappe.clear_document_cache, "Habitat Settings", "Habitat Settings")

        self.cost_center = frappe.db.get_value("Building", BUILDING, "default_cost_center")
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})
        self.project = frappe.db.get_value("Project", {"project_name": "_Test Project"})
        frappe.db.set_value("Building", BUILDING, "annual_rent", ANNUAL_RENT)

    def _assignment(self, **overrides):
        payload = {
            "doctype": "Housing Assignment",
            "employee": self.employee,
            "project": self.project,
            "cost_center": self.cost_center,
            "building": BUILDING,
            "room": ROOM,
            "bed": BED,
            "check_in_date": getdate(),
            "assignment_type": "New Assignment",
        }
        payload.update(overrides)
        doc = frappe.get_doc(payload)
        doc.insert(ignore_permissions=True)
        doc.submit()
        return doc

    def test_the_allocation_carries_the_supplier_down_and_the_report_adds_the_markup(self):
        assignment = self._assignment(is_external_supplier=1, billed_to_supplier=SUPPLIER)

        settings = frappe.get_single("Habitat Settings")
        settings.enable_supplier_markup = 1
        settings.supplier_markup_percent = 5.0
        settings.save(ignore_permissions=True)

        allocate_building_accommodation_cost(BUILDING)

        rows = frappe.get_all(
            "Accommodation Ledger",
            filters={"assignment": assignment.name},
            fields=["billed_to_supplier", "employee_daily_share"],
        )
        self.assertTrue(rows, "the daily allocation created no ledger rows")
        self.assertTrue(
            all(r.billed_to_supplier == SUPPLIER for r in rows),
            "billed_to_supplier was not propagated to the ledger",
        )
        base = flt(sum(flt(r.employee_daily_share) for r in rows), 2)
        self.assertGreater(base, 0, "expected a non-zero daily share from the annual rent")

        today = getdate()
        _columns, data, *_rest = execute({"month": today.month, "year": today.year, "supplier": SUPPLIER})
        mine = [d for d in data if d["billed_to_supplier"] == SUPPLIER and d["employee"] == self.employee]
        self.assertEqual(len(mine), 1, "the supplier/employee row is missing from the report")

        row = mine[0]
        self.assertGreaterEqual(row["days_housed"], 1)
        self.assertAlmostEqual(row["base_cost"], base, places=2)
        self.assertAlmostEqual(row["markup"], flt(base * 0.05, 2), places=2)
        self.assertAlmostEqual(row["total_deduction"], flt(base + base * 0.05, 2), places=2)

    def test_the_dispatcher_hands_each_building_to_its_own_long_queue_job(self):
        self._assignment()

        with patch("apex.habitat.tasks.cost.frappe.enqueue") as enqueue:
            daily_accommodation_cost_allocation()

        buildings = [call.kwargs.get("building") for call in enqueue.call_args_list]
        self.assertIn(BUILDING, buildings, "the dispatcher did not enqueue this building")
        self.assertTrue(
            all(call.kwargs.get("queue") == "long" for call in enqueue.call_args_list),
            "per-building jobs must run on the long queue",
        )
        self.assertTrue(
            all(
                call.args[0] == "apex.habitat.tasks.cost.allocate_building_accommodation_cost"
                for call in enqueue.call_args_list
            ),
            "the dispatcher must enqueue the per-building worker",
        )
