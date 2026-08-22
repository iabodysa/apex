# Copyright (c) 2026, afmcoltd
"""Contract test for ``seed_catalog`` inserts every catalog entry
that does not already exist, and is idempotent — a second run creates nothing
new and raises nothing."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.maintenance_material.maintenance_material_catalog import (
    MAINTENANCE_MATERIAL_CATALOG,
    seed_catalog,
)

class TestSeedCatalog(FrappeTestCase):
    def test_seeds_every_catalog_entry(self):
        seed_catalog()
        for item in MAINTENANCE_MATERIAL_CATALOG:
            self.assertTrue(
                frappe.db.exists("Maintenance Material", item["material_name"]),
                f"{item['material_name']} was not seeded",
            )

    def test_seeded_rows_carry_the_catalog_fields(self):
        seed_catalog()
        sample = MAINTENANCE_MATERIAL_CATALOG[0]
        row = frappe.db.get_value(
            "Maintenance Material",
            sample["material_name"],
            ["material_category", "default_uom", "is_active"],
            as_dict=True,
        )
        self.assertEqual(row.material_category, sample["material_category"])
        self.assertEqual(row.default_uom, sample.get("default_uom", "Piece"))
        self.assertEqual(row.is_active, 1)

    def test_is_idempotent_on_a_second_run(self):
        seed_catalog()
        before = frappe.db.count("Maintenance Material")
        seed_catalog()
        after = frappe.db.count("Maintenance Material")
        self.assertEqual(before, after)

    def test_does_not_overwrite_a_pre_existing_row(self):
        sample_name = MAINTENANCE_MATERIAL_CATALOG[0]["material_name"]
        if not frappe.db.exists("Maintenance Material", sample_name):
            frappe.get_doc(
                {
                    "doctype": "Maintenance Material",
                    "material_name": sample_name,
                    "material_category": MAINTENANCE_MATERIAL_CATALOG[0]["material_category"],
                    "is_active": 1,
                }
            ).insert(ignore_permissions=True)
            frappe.db.commit()

        def _restore():
            frappe.db.set_value("Maintenance Material", sample_name, "is_active", 1)
            frappe.db.commit()

        self.addCleanup(_restore)

        frappe.db.set_value("Maintenance Material", sample_name, "is_active", 0)
        frappe.db.commit()
        seed_catalog()
        self.assertEqual(frappe.db.get_value("Maintenance Material", sample_name, "is_active"), 0)
