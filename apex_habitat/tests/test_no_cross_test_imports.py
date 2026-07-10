# Copyright (c) 2026, AFMCO and contributors
"""Release-hygiene guard (P-129): no NEW cross-test-module imports.

A test module must NOT import fixture helpers from a sibling ``test_*`` module —
shared builders belong in ``tests/factories.py``. This guard AST-scans every
``tests/*.py`` for ``from apex_habitat.tests.test_<x> import ...`` (and the bare
``import apex_habitat.tests.test_<x>``) and fails if any appears that is not in the
frozen ``_BASELINE`` of pre-existing debt.

The baseline is now EMPTY (P-135 retired all 44 pairs — every shared helper and
the base ``ApexHabitatTestCase`` were promoted into ``tests/factories.py``). The
ratchet is therefore absolute: ANY ``from apex_habitat.tests.test_<x> import ...``
in ``tests/*.py`` fails this test. Put the shared fixture in ``tests/factories.py``
(a non-``test_*`` module) instead of importing from a sibling test module.
"""

import ast
import glob
import os
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PREFIX = "apex_habitat.tests.test_"

# Retired to EMPTY at P-135. Every historical coupling was cleaned: the base
# ``ApexHabitatTestCase`` moved to factories.py (test_utils.py now re-exports it for
# the DocType-level tests outside this scope), and the driver-portal + Masar
# worker-movement helper hubs (``_ensure_test_driver``, ``_WorkerTripMixin``,
# ``_building``/``_employee``/``_project``/…) are all consumed from factories.py now.
# Do NOT add entries here — put the shared fixture in factories.py.
_BASELINE = frozenset()

# Files that must stay 100% free of cross-test-module imports. Seeded by P-129 and
# extended by every P-135 batch as each coupling was redirected into factories.py.
_MUST_BE_CLEAN = frozenset(
    {
        # P-129 / earlier driver-portal cleanups
        "test_driver_gps_eta.py",
        "test_masar_worker_movement.py",
        "test_driver_portal_attendance.py",
        "test_driver_portal_enrich.py",
        "test_driver_portal_flag.py",
        "test_driver_portal_push.py",
        "test_driver_portal_today.py",
        "test_salis_controls.py",
        # P-135 base-TestCase batch (ApexHabitatTestCase -> factories)
        "test_accommodation_material_transfer.py",
        "test_accommodation_stock_ledger.py",
        "test_backfill_assignment_facility_supervisor.py",
        "test_consumable_custody_expiry.py",
        "test_custody_stock_integration.py",
        "test_financial_side_effects.py",
        "test_form_dashboards.py",
        "test_front_desk.py",
        "test_housing_lifecycle.py",
        "test_idempotency_guards.py",
        "test_material_template_coverage.py",
        "test_my_work_center.py",
        "test_occupancy_snapshot.py",
        "test_qa_probe_systems.py",
        "test_qa_probe_transactions.py",
        "test_reports.py",
        "test_resident_request_convert.py",
        "test_resident_request_todo.py",
        "test_safety_zero_rounds_scan.py",
        "test_supplier_cost_recovery.py",
        "test_temporary_stay_and_idle.py",
        "test_v0_9_0_pages.py",
        # P-135 Masar / driver-portal helper-hub batch
        "test_boarding_scan.py",
        "test_driver_portal.py",
        "test_driver_portal_scope.py",
        "test_masar_1b.py",
        "test_masar_n1_prefetch.py",
        "test_masar_worker_boarding_confirm.py",
        "test_masar_worker_contacts.py",
        "test_masar_worker_scope.py",
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
