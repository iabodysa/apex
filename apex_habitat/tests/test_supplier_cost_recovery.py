# Copyright (c) 2026, AFMCO and contributors
"""End-to-end test for Supplier Accommodation Cost Recovery:
daily allocation propagates billed_to_supplier to the ledger, and the
Supplier Cost Recovery report aggregates the month with the markup applied."""

import frappe
from frappe.utils import flt, getdate
from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.habitat.tasks import daily_accommodation_cost_allocation
from apex_habitat.habitat.report.supplier_cost_recovery.supplier_cost_recovery import execute


def _h(n=4):
    return frappe.generate_hash(length=n).upper()


class TestSupplierCostRecovery(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia",
        }).insert(ignore_permissions=True).name
        self.cost_center = (frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company})
                            or frappe.db.get_value("Cost Center", {"is_group": 0}))
        self.project = frappe.db.get_value("Project", {}) or frappe.get_doc({
            "doctype": "Project", "project_name": "P " + _h(), "company": self.company,
        }).insert(ignore_permissions=True).name
        self.employee = frappe.get_doc({
            "doctype": "Employee", "first_name": "Sup Emp " + _h(), "company": self.company,
            "gender": "Male", "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01",
        }).insert(ignore_permissions=True).name
        self.supplier = frappe.get_doc({
            "doctype": "Supplier", "supplier_name": "Vendor " + _h(),
            "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}),
        }).insert(ignore_permissions=True).name
        self.site = frappe.get_doc({"doctype": "Accommodation Site", "site_name": _h(6)}).insert(ignore_permissions=True)
        self.building = frappe.get_doc({
            "doctype": "Accommodation Building", "building_name": "B " + _h(), "site": self.site.name,
            "total_capacity": 10, "default_cost_center": self.cost_center,
            "annual_rent_sar": 36500,
        }).insert(ignore_permissions=True)
        self.room = frappe.get_doc({
            "doctype": "Accommodation Room", "naming_series": "ROOM-.####",
            "building": self.building.name, "room_number": "R" + _h(), "bed_capacity": 2,
        }).insert(ignore_permissions=True).name
        self.bed = frappe.get_doc({
            "doctype": "Accommodation Bed", "naming_series": "BED-.####",
            "room": self.room, "bed_code": "B" + _h(),
        }).insert(ignore_permissions=True).name

    def test_supplier_propagation_and_report_markup(self):
        # tag an assignment as external-supplier
        a = frappe.get_doc({
            "doctype": "Accommodation Assignment", "employee": self.employee, "project": self.project,
            "cost_center": self.cost_center, "building": self.building.name, "room": self.room,
            "bed": self.bed, "check_in_date": getdate(), "assignment_type": "New Assignment",
            "is_external_supplier": 1, "billed_to_supplier": self.supplier,
        })
        a.insert(ignore_permissions=True)
        a.submit()

        # enable a 5% markup
        settings = frappe.get_single("Habitat Settings")
        settings.enable_supplier_markup = 1
        settings.supplier_markup_percent = 5.0
        settings.save(ignore_permissions=True)

        daily_accommodation_cost_allocation()

        # ledger rows for this assignment must carry the supplier
        rows = frappe.get_all("Accommodation Ledger",
                              filters={"assignment": a.name},
                              fields=["billed_to_supplier", "employee_daily_share"])
        self.assertTrue(rows, "daily allocation created no ledger rows")
        self.assertTrue(all(r.billed_to_supplier == self.supplier for r in rows),
                        "billed_to_supplier was not propagated to the ledger")
        base = flt(sum(flt(r.employee_daily_share) for r in rows), 2)
        self.assertGreater(base, 0, "expected a non-zero daily share from annual_rent")

        # report aggregates the month and applies the 5% markup
        today = getdate()
        columns, data = execute({"month": today.month, "year": today.year, "supplier": self.supplier})
        mine = [d for d in data if d["billed_to_supplier"] == self.supplier and d["employee"] == self.employee]
        self.assertEqual(len(mine), 1, "supplier/employee row missing from report")
        row = mine[0]
        self.assertGreaterEqual(row["days_housed"], 1)
        self.assertAlmostEqual(row["base_cost"], base, places=2)
        self.assertAlmostEqual(row["markup"], flt(base * 0.05, 2), places=2)
        self.assertAlmostEqual(row["total_deduction"], flt(base + base * 0.05, 2), places=2)
