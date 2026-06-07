"""Parity guards: the externalised shared seed JSON must exactly match the
records the legacy ``*_seed.py`` modules intend to insert.

These tests are pure (no site needed): ``load_specs`` has no ``frappe``
dependency, and the legacy seeders import ``frappe`` only at module top but
never touch it at import time — their data lives in module-level constants, so
we can reconstruct the *effective* inserted records and diff them against the
JSON the loader will apply.

Covered:
- habitat/maintenance_material.json          <- single JSON source (MATERIAL_SEEDS retired, T-050#3)
- habitat/maintenance_material_template.json <- maintenance_material_template_seed.TEMPLATE_SEEDS
- salis/issue_type.json                      <- issue_seed._ISSUE_TYPES
- salis/issue_priority.json                  <- issue_seed._ISSUE_PRIORITIES
- salis/service_level_agreement.json         <- issue_seed._SLA_* / _WORKDAYS

NOTE on the SLA: the legacy ``_seed_sla`` also sets a *runtime-resolved*
``holiday_list`` (picked per-site from Company / HR Settings) and toggles
``Support Settings.track_service_level_agreement`` imperatively. Those cannot be
captured as static, site-independent JSON, so the JSON intentionally omits
``holiday_list``. This test asserts parity on every static field the seeder sets
and documents the dynamic field as a known, deliberate gap.
"""

import unittest

from apex_habitat.apex_core.setup.seed import load_specs


def _spec(module_dir, doctype):
    specs = load_specs(module_dir, only=[doctype])
    assert len(specs) == 1, f"expected exactly one spec for {doctype}, got {len(specs)}"
    return specs[0]


class TestMaintenanceMaterialParity(unittest.TestCase):
    def test_maintenance_material_spec_loads(self):
        # MATERIAL_SEEDS was retired (T-050#3): habitat/maintenance_material.json is
        # now the SINGLE source of truth, so there is no second source to diff. Assert
        # the JSON still loads through the shared loader with the expected shape.
        spec = _spec("habitat", "Maintenance Material")
        self.assertEqual(spec["key"], "material_name")
        self.assertTrue(spec["create_only"])
        self.assertTrue(spec["records"], "maintenance_material.json must not be empty")
        for rec in spec["records"]:
            self.assertIn("material_name", rec)
            self.assertIn("material_category", rec)
            self.assertEqual(rec.get("is_active"), 1)

    def test_maintenance_material_template_parity(self):
        from apex_habitat.apex_core.setup.seeders.maintenance_material_template_seed import (
            TEMPLATE_SEEDS,
        )

        spec = _spec("habitat", "Maintenance Material Template")
        self.assertEqual(spec["key"], "template_name")
        self.assertTrue(spec["create_only"])

        # The seeder inserts template_name + issue_type + is_active=1 + items[]
        # (each item: material + quantity, copied verbatim from the source).
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


class TestSalisIssueMasterParity(unittest.TestCase):
    def test_issue_type_parity(self):
        from apex_habitat.apex_core.setup.seeders.salis_issue_seed import _ISSUE_TYPES

        spec = _spec("salis", "Issue Type")
        self.assertEqual(spec["key"], "name")
        self.assertTrue(spec["create_only"])
        self.assertEqual(spec["records"], [{"name": n} for n in _ISSUE_TYPES])

    def test_issue_priority_parity(self):
        from apex_habitat.apex_core.setup.seeders.salis_issue_seed import _ISSUE_PRIORITIES

        spec = _spec("salis", "Issue Priority")
        self.assertEqual(spec["key"], "name")
        self.assertTrue(spec["create_only"])
        self.assertEqual(spec["records"], [{"name": n} for n in _ISSUE_PRIORITIES])

    def test_service_level_agreement_static_parity(self):
        from apex_habitat.apex_core.setup.seeders import salis_issue_seed as issue_seed

        spec = _spec("salis", "Service Level Agreement")
        self.assertEqual(spec["key"], "service_level")
        self.assertTrue(spec["create_only"])
        self.assertEqual(len(spec["records"]), 1)
        rec = spec["records"][0]

        # Scalar header fields the seeder sets (all but the dynamic holiday_list).
        self.assertEqual(rec["service_level"], issue_seed._SLA_NAME)
        self.assertEqual(rec["document_type"], "Issue")
        self.assertEqual(rec["default_service_level_agreement"], 1)
        self.assertEqual(rec["enabled"], 1)
        self.assertEqual(rec["apply_sla_for_resolution"], 1)

        # holiday_list is resolved per-site at runtime — it MUST NOT be in the
        # static JSON (this asserts the deliberate gap, so a future edit that
        # hardcodes a site-specific holiday list fails this test loudly).
        self.assertNotIn("holiday_list", rec)

        # priorities child rows, in source order, with the seeder's seconds math.
        expected_priorities = [
            {
                "priority": priority,
                "response_time": response,
                "resolution_time": resolution,
                "default_priority": is_default,
            }
            for priority, response, resolution, is_default in issue_seed._SLA_PRIORITIES
        ]
        self.assertEqual(rec["priorities"], expected_priorities)

        # 24x7 support window, one full-day row per weekday in source order.
        expected_window = [
            {"workday": day, "start_time": "00:00:00", "end_time": "23:59:59"}
            for day in issue_seed._WORKDAYS
        ]
        self.assertEqual(rec["support_and_resolution"], expected_window)

        # SLA fulfilled when the Issue reaches a terminal state.
        self.assertEqual(
            rec["sla_fulfilled_on"],
            [{"status": "Resolved"}, {"status": "Closed"}],
        )


if __name__ == "__main__":
    unittest.main()
