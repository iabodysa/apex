"""Seed Maintenance Material catalog items and templates for issue types that
previously had no template (Fire Safety, Furniture, Pest Control, Structural).

Before this, "Load Material Template" on a Maintenance Request with one of those
issue types returned "No active template found for issue type: ...". The seed
function is idempotent (checks existence per material and per template).
"""

import frappe
from apex_habitat.habitat.doctype.maintenance_material_template.maintenance_material_template_seed import (
    seed_templates,
)


def execute():
    try:
        seed_templates()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_missing_material_templates failed",
            message=frappe.get_traceback(),
        )
        raise
