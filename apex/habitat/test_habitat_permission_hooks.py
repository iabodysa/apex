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
  4. The `Maintenance Request` `before_save` controller hook in `doc_events` is
     left intact (the new scoping wiring is additive, never a replacement).

Role provisioning is intentionally NOT a fixture (A-101): it moved to the
idempotent Python provisioners, so there is no Role-fixture guard here.

Run standalone:  python3 -m unittest tests.test_habitat_permission_hooks -v
"""

import unittest


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

    def test_doc_events_before_save_left_intact(self):
        # [#l5c86z]
        self.assertEqual(
            self.hooks.doc_events["Maintenance Request"]["before_save"],
            "apex.habitat.doctype.maintenance_request."
            "maintenance_request.before_save",
        )


if __name__ == "__main__":
    unittest.main()
