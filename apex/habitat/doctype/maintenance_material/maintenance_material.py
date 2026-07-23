# Copyright (c) 2026, AFMCO and contributors
"""Maintenance Material controller (native NestedSet tree)."""
from frappe.utils.nestedset import NestedSet


class MaintenanceMaterial(NestedSet):
    # [#bc52av]
    def on_update(self):
        NestedSet.on_update(self)
        self.validate_one_root()

    def on_trash(self):
        NestedSet.on_trash(self, allow_root_deletion=True)
