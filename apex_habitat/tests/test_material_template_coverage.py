# Copyright (c) 2026, AFMCO and contributors
"""Regression: every Maintenance Request issue type (except the catch-all
"Other") must have at least one active Maintenance Material Template, so
"Load Material Template" never dead-ends with "No active template found".
"""

import frappe
from apex_habitat.tests.factories import ApexHabitatTestCase
from apex_habitat.apex_core.setup.seeders.maintenance_material_template_seed import (
    seed_templates,
)


class TestMaterialTemplateCoverage(ApexHabitatTestCase):
    def test_every_issue_type_has_active_template(self):
        seed_templates()  # [#1jpp39]

        meta = frappe.get_meta("Maintenance Request")
        issue_field = meta.get_field("issue_type")
        options = [o.strip() for o in (issue_field.options or "").split("\n") if o.strip()]

        # [#eqixfg]
        expected = [o for o in options if o != "Other"]
        self.assertTrue(expected, "no issue_type options found")

        missing = [
            it for it in expected
            if not frappe.db.exists(
                "Maintenance Material Template", {"issue_type": it, "is_active": 1}
            )
        ]
        self.assertEqual(
            missing, [],
            f"Issue types with no active material template: {missing}",
        )
