# Copyright (c) 2026, AFMCO and contributors
"""Parity guards: the externalised shared seed JSON must exactly match the
records the legacy ``*_seed.py`` modules intend to insert.

These tests are pure (no site needed): ``load_specs`` has no ``frappe``
dependency, and the legacy seeders import ``frappe`` only at module top but
never touch it at import time — their data lives in module-level constants, so
we can reconstruct the *effective* inserted records and diff them against the
JSON the loader will apply.

Covered:
- habitat/maintenance_material.json          <- single JSON source (MATERIAL_SEEDS retired)
- habitat/maintenance_material_template.json <- maintenance_material_template_seed.TEMPLATE_SEEDS

The salis Issue Type / Issue Priority / Service Level Agreement parity checks are not
here: ``salis_issue_seed`` carries no JSON-spec source for them (``apex_core/setup/data/salis/``
has no ``service_level_agreement`` spec), and the Salis support desk is seeded natively by
``apex_core/setup/salis_support.py``, which this loader-parity file has no reason to
duplicate.
"""

import unittest

from apex.apex_core.setup.seed import load_specs


def _spec(module_dir, doctype):
    specs = load_specs(module_dir, only=[doctype])
    assert len(specs) == 1, f"expected exactly one spec for {doctype}, got {len(specs)}"
    return specs[0]


class TestMaintenanceMaterialParity(unittest.TestCase):
    def test_maintenance_material_spec_loads(self):
        spec = _spec("habitat", "Maintenance Material")
        self.assertEqual(spec["key"], "material_name")
        self.assertTrue(spec["create_only"])
        self.assertTrue(spec["records"], "maintenance_material.json must not be empty")
        for rec in spec["records"]:
            self.assertIn("material_name", rec)
            self.assertIn("material_category", rec)
            self.assertEqual(rec.get("is_active"), 1)

    def test_maintenance_material_template_parity(self):
        from apex.apex_core.setup.seeders.maintenance_material_template_seed import (
            TEMPLATE_SEEDS,
        )

        spec = _spec("habitat", "Maintenance Material Template")
        self.assertEqual(spec["key"], "template_name")
        self.assertTrue(spec["create_only"])

        expected = [
            {
                "template_name": t["template_name"],
                "issue_type": t["issue_type"],
                "is_active": 1,
                "items": [
                    {"material": i["material"], "quantity": i["quantity"]}
                    for i in t["items"]
                ],
            }
            for t in TEMPLATE_SEEDS
        ]
        self.assertEqual(spec["records"], expected)
        self.assertEqual(len(spec["records"]), len(TEMPLATE_SEEDS))


if __name__ == "__main__":
    unittest.main()
