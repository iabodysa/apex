# Copyright (c) 2026, AFMCO and contributors
"""Release-hygiene guard (P-129): no NEW cross-test-module imports.

A test module must NOT import fixture helpers from a sibling ``test_*`` module —
shared builders belong in ``tests/factories.py``. This guard AST-scans every
``tests/*.py`` for ``from apex_habitat.tests.test_<x> import ...`` (and the bare
``import apex_habitat.tests.test_<x>``) and fails if any appears that is not in the
frozen ``_BASELINE`` of pre-existing debt.

The baseline is a ratchet: it may only shrink. Adding a new cross-test-module
import (or re-introducing one into a file already cleaned — e.g. the two P-129
targets below, which are deliberately absent from the baseline) fails this test.
Cleaning an existing entry is welcome; drop it from ``_BASELINE`` when you do.
"""

import ast
import glob
import os
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PREFIX = "apex_habitat.tests.test_"

# Frozen at P-129. Each pair is (test_module_filename, imported_test_module). These
# are the shared-helper couplings that predate the factories-library migration and
# are out of P-129's scope (mostly the ``test_utils`` base TestCase, the
# ``_ensure_test_driver`` / ``_driver_without_vehicle`` driver-portal hubs, and the
# Masar worker-movement helper hub). Do NOT add to this set.
_BASELINE = frozenset(
    {
        ("test_accommodation_material_transfer.py", "apex_habitat.tests.test_utils"),
        ("test_accommodation_stock_ledger.py", "apex_habitat.tests.test_utils"),
        ("test_backfill_assignment_facility_supervisor.py", "apex_habitat.tests.test_utils"),
        ("test_boarding_scan.py", "apex_habitat.tests.test_driver_portal"),
        ("test_boarding_scan.py", "apex_habitat.tests.test_masar_worker_movement"),
        ("test_consumable_custody_expiry.py", "apex_habitat.tests.test_utils"),
        ("test_custody_stock_integration.py", "apex_habitat.tests.test_utils"),
        ("test_driver_portal.py", "apex_habitat.tests.test_masar_worker_movement"),
        ("test_driver_portal_scope.py", "apex_habitat.tests.test_driver_portal"),
        ("test_financial_side_effects.py", "apex_habitat.tests.test_utils"),
        ("test_form_dashboards.py", "apex_habitat.tests.test_utils"),
        ("test_front_desk.py", "apex_habitat.tests.test_utils"),
        ("test_housing_lifecycle.py", "apex_habitat.tests.test_utils"),
        ("test_idempotency_guards.py", "apex_habitat.tests.test_utils"),
        ("test_masar_1b.py", "apex_habitat.tests.test_driver_portal"),
        ("test_masar_1b.py", "apex_habitat.tests.test_masar_worker_movement"),
        ("test_masar_n1_prefetch.py", "apex_habitat.tests.test_masar_worker_movement"),
        ("test_masar_worker_boarding_confirm.py", "apex_habitat.tests.test_driver_portal"),
        ("test_masar_worker_boarding_confirm.py", "apex_habitat.tests.test_masar_worker_movement"),
        ("test_masar_worker_contacts.py", "apex_habitat.tests.test_driver_portal"),
        ("test_masar_worker_contacts.py", "apex_habitat.tests.test_masar_worker_movement"),
        ("test_masar_worker_scope.py", "apex_habitat.tests.test_driver_portal"),
        ("test_masar_worker_scope.py", "apex_habitat.tests.test_masar_worker_movement"),
        ("test_material_template_coverage.py", "apex_habitat.tests.test_utils"),
        ("test_my_work_center.py", "apex_habitat.tests.test_utils"),
        ("test_occupancy_snapshot.py", "apex_habitat.tests.test_utils"),
        ("test_qa_probe_systems.py", "apex_habitat.tests.test_utils"),
        ("test_qa_probe_transactions.py", "apex_habitat.tests.test_utils"),
        ("test_reports.py", "apex_habitat.tests.test_utils"),
        ("test_resident_request_convert.py", "apex_habitat.tests.test_utils"),
        ("test_resident_request_todo.py", "apex_habitat.tests.test_utils"),
        ("test_safety_zero_rounds_scan.py", "apex_habitat.tests.test_utils"),
        ("test_supplier_cost_recovery.py", "apex_habitat.tests.test_utils"),
        ("test_temporary_stay_and_idle.py", "apex_habitat.tests.test_utils"),
        ("test_v0_9_0_pages.py", "apex_habitat.tests.test_utils"),
    }
)

# Files that must stay 100% free of cross-test-module imports (cleaned by P-129 and
# the P-135 baseline-retirement batches). The driver-portal batch (P-135) redirected
# _ensure_test_driver -> factories.make_test_driver and _driver_without_vehicle ->
# factories.make_driver_without_vehicle across these consumers.
_MUST_BE_CLEAN = frozenset(
    {
        "test_driver_gps_eta.py",
        "test_masar_worker_movement.py",
        "test_driver_portal_attendance.py",
        "test_driver_portal_enrich.py",
        "test_driver_portal_flag.py",
        "test_driver_portal_push.py",
        "test_driver_portal_today.py",
        "test_salis_controls.py",
    }
)


def _scan():
    """Return the set of (filename, imported_test_module) pairs across tests/*.py."""
    found = set()
    for path in sorted(glob.glob(os.path.join(_TESTS_DIR, "*.py"))):
        base = os.path.basename(path)
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=base)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith(_PREFIX):
                    found.add((base, node.module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(_PREFIX):
                        found.add((base, alias.name))
    return found


class TestNoCrossTestImports(unittest.TestCase):
    def test_no_new_cross_test_module_imports(self):
        found = _scan()
        new = found - _BASELINE
        self.assertEqual(
            new,
            set(),
            "New cross-test-module import(s) detected. Move the shared fixture into "
            "tests/factories.py instead of importing from a sibling test module:\n"
            + "\n".join(f"  {f} -> {m}" for f, m in sorted(new)),
        )

    def test_cleaned_files_have_no_cross_test_imports(self):
        offenders = sorted(
            (f, m) for (f, m) in _scan() if f in _MUST_BE_CLEAN
        )
        self.assertEqual(
            offenders,
            [],
            "A P-129-cleaned file re-introduced a cross-test-module import:\n"
            + "\n".join(f"  {f} -> {m}" for f, m in offenders),
        )


if __name__ == "__main__":
    unittest.main()
