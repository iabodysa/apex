# Copyright (c) 2026, AFMCO and contributors
"""Maintenance Material controller (flat catalog).

Deliberately NOT a NestedSet. `material_category` already carries the only
taxonomy this catalog has, so a parent/child tree could only mirror it. The tree
never held data either: all 98 seeded materials insert parentless, and the
shipped install survived `validate_one_root` only because
`get_root_node_count` counts `parent_maintenance_material = ''` while an unset
Link writes NULL -- give that column a `''` default and the install aborted on
record 2 of 98.
"""
from frappe.model.document import Document


class MaintenanceMaterial(Document):
    pass
