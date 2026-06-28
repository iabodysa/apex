# Copyright (c) 2026, AFMCO and contributors
"""Maintenance Material controller (native NestedSet tree)."""
from frappe.utils.nestedset import NestedSet


class MaintenanceMaterial(NestedSet):
    # NestedSet maintains lft/rgt; enforce a single tree root.
    def on_update(self):
        NestedSet.on_update(self)
        self.validate_one_root()

    def on_trash(self):
        NestedSet.on_trash(self, allow_root_deletion=True)
