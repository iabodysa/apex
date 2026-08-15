# Copyright (c) 2026, AFMCO and contributors
"""Wiring guards for the Habitat owner-scoped Maintenance Request hooks.

These are pure-Python tests (no live Frappe site required): they import the
`apex.hooks` module — which declares no top-level `import frappe`, so it
loads without a bench — and assert the registration dicts are wired exactly
as the owner-scoping design requires.

What they lock in:

  1. `permission_query_conditions["Maintenance Request"]` points at the Habitat
     module's `maintenance_request_query` (not the Salis module, and not the
     `before_save` controller hook that lives in `doc_events`).
  2. `has_permission["Maintenance Request"]` points at the Habitat module's
     `maintenance_request_has_permission`.
  3. Both referenced functions actually exist in
     `apex.habitat.permissions` (so a typo in the dotted path is caught
     here, not at runtime on a customer site).
  4. The `Maintenance Request` controller hook in `doc_events` is left intact (the
     scoping wiring is additive, never a replacement). That hook is `validate`, not
     `before_save`: the controller ships `validate` and no `before_save` at all.

Role provisioning is intentionally NOT a fixture (A-101): it moved to the
idempotent Python provisioners, so there is no Role-fixture guard here.

Standalone stub (A-205)
-----------------------
`apex.hooks` needs nothing, but guards 3 and 4 import the real
`apex.habitat.permissions`, which — with `apex.apex_core.utils.permission_scope`
behind it — does `import frappe` at module scope, so the command below needs a
fallback. A BARE module is the whole stub. Same idiom as
`apex_core/utils/test_guarded_index_dedupe.py`; under bench the REAL frappe is
already in `sys.modules` and the branch never runs.

The assertions keep their full meaning: those imports still resolve the REAL
permissions module and look up the REAL function names, so a typo in either dotted
path still fails exactly as intended. Neither guard CALLS the resolved functions, so
nothing can pass on the stub's behalf — a call would touch an attribute this stub
does not define and raise.

Run standalone:  python3 -m unittest apex.habitat.test_habitat_permission_hooks -v
"""

import sys
import types
import unittest

# Load-bearing only off-bench — see "Standalone stub" in the module docstring
# for why a bare module is the whole stub and cannot fake a pass.
if "frappe" not in sys.modules:
    sys.modules["frappe"] = types.ModuleType("frappe")


class TestMaintenanceRequestScopingWiring(unittest.TestCase):
    """permission_query_conditions / has_permission entries for the owner-scope."""

    QUERY_FN = "apex.habitat.permissions.maintenance_request_query"
    HAS_PERM_FN = "apex.habitat.permissions.maintenance_request_has_permission"

    def setUp(self):
        import apex.hooks as hooks

        self.hooks = hooks

    def test_permission_query_conditions_wired(self):
        self.assertEqual(
            self.hooks.permission_query_conditions.get("Maintenance Request"),
            self.QUERY_FN,
        )

    def test_has_permission_wired(self):
        self.assertEqual(
            self.hooks.has_permission.get("Maintenance Request"),
            self.HAS_PERM_FN,
        )

    def test_query_target_is_importable(self):
        from apex.habitat.permissions import maintenance_request_query

        self.assertTrue(callable(maintenance_request_query))

    def test_has_permission_target_is_importable(self):
        from apex.habitat.permissions import (
            maintenance_request_has_permission,
        )

        self.assertTrue(callable(maintenance_request_has_permission))

    def test_doc_events_controller_hook_left_intact(self):
        """The scoping wiring lives in its own two dicts, so the controller event must
        still be registered beside it rather than replaced by it."""
        self.assertEqual(
            self.hooks.doc_events["Maintenance Request"],
            {"validate": "apex.habitat.doctype.maintenance_request."
                         "maintenance_request.validate"},
        )


if __name__ == "__main__":
    unittest.main()
