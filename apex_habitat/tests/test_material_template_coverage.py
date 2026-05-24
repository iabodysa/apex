# Copyright (c) 2026, AFMCO and contributors
"""Regression: every Maintenance Request issue type (except the catch-all
"Other") must have at least one active Maintenance Material Template, so
"Load Material Template" never dead-ends with "No active template found".
"""

import frappe
from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.habitat.doctype.maintenance_material_template.maintenance_material_template_seed import (
    seed_templates,
)


class TestMaterialTemplateCoverage(ApexHabitatTestCase):
    def test_every_issue_type_has_active_template(self):
        seed_templates()  # idempotent

        meta = frappe.get_meta("Maintenance Request")
        issue_field = meta.get_field("issue_type")
        options = [o.strip() for o in (issue_field.options or "").split("\n") if o.strip()]

        # "Other" is an intentional catch-all with no dedicated template.
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
