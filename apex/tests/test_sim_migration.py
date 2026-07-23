# Copyright (c) 2026, AFMCO and contributors
"""SIM Card Management migration: dry-run counts are exact, migratable rows become
SIM + contract + opening custody, ambiguous rows are quarantined (not guessed), and
re-running creates no duplicates. Exercised against a synthetic legacy source
DocType so the create-path is verified without the real site data."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_0 import migrate_sim_card_management as migration
from apex.tests import factories

SOURCE = "SIM Card Management"


class TestSIMMigration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = factories.make_company("Test AFMCO").name
        cls.employee = factories.make_employee("Legacy Holder", company=cls.company).name
        cls.supplier = "QA Legacy Telco"
        if not frappe.db.exists("Supplier", cls.supplier):
            frappe.get_doc(
                {"doctype": "Supplier", "supplier_name": cls.supplier, "supplier_group": "All Supplier Groups"}
            ).insert(ignore_permissions=True)
        cls._make_source_doctype()
        cls._seed_rows()
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.db.set_value("DocType", SOURCE, "read_only", 0)
        frappe.db.delete(SOURCE)
        if frappe.db.exists("DocType", SOURCE):
            frappe.delete_doc("DocType", SOURCE, force=True, ignore_permissions=True)
        frappe.db.commit()
        super().tearDownClass()

    @classmethod
    def _make_source_doctype(cls):
        if frappe.db.exists("DocType", SOURCE):
            return
        frappe.get_doc(
            {
                "doctype": "DocType",
                "name": SOURCE,
                "module": "Custom",
                "custom": 1,
                "fields": [
                    {"fieldname": "mobile_number", "fieldtype": "Data", "label": "Mobile Number"},
                    {"fieldname": "iccid", "fieldtype": "Data", "label": "ICCID"},
                    {"fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "label": "Supplier"},
                    {"fieldname": "company", "fieldtype": "Link", "options": "Company", "label": "Company"},
                    {"fieldname": "employee", "fieldtype": "Link", "options": "Employee", "label": "Employee"},
                ],
                "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1}],
            }
        ).insert(ignore_permissions=True)

    @classmethod
    def _seed_rows(cls):
        rows = [
            {"mobile_number": "055 111 2233", "iccid": "8996-1", "supplier": cls.supplier, "company": cls.company, "employee": cls.employee},
            {"mobile_number": "0551119999", "company": cls.company},  # ambiguous: no supplier
            {"iccid": "8996-3", "supplier": cls.supplier, "company": cls.company},  # rejected: no mobile
        ]
        for r in rows:
            doc = frappe.new_doc(SOURCE)
            doc.update(r)
            doc.insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()

    def test_dry_run_counts_are_exact(self):
        summary = migration.dry_run()
        self.assertEqual(summary["source"], 3)
        self.assertEqual(summary["migratable"], 1)
        self.assertEqual(summary["ambiguous"], 1)
        self.assertEqual(summary["rejected"], 1)
        self.assertEqual(len(summary["quarantined_rows"]), 1)

    def test_migration_creates_sim_contract_and_opening_custody(self):
        migration.execute()
        sim = frappe.db.get_value("SIM Card", {"mobile_number_normalized": "0551112233"}, "name")
        self.assertTrue(sim)
        self.assertEqual(frappe.db.get_value("SIM Card", sim, "status"), "Assigned")
        self.assertEqual(
            frappe.db.count("SIM Custody Assignment", {"sim_card": sim, "docstatus": 1}), 1
        )

    def test_migration_is_idempotent(self):
        migration.execute()
        migration.execute()
        self.assertEqual(
            frappe.db.count("SIM Card", {"mobile_number_normalized": "0551112233"}), 1
        )
