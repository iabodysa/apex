# Copyright (c) 2026, AFMCO and contributors
"""Release-hygiene guard (P-129): no NEW cross-test-module imports.

A test module must NOT import fixture helpers from a sibling ``test_*`` module —
shared builders belong in ``tests/factories.py``. This guard AST-scans every
``test_*.py`` ANYWHERE under ``apex/`` and fails on any import whose target
module's final segment starts with ``test_`` (absolute ``from apex.x.test_y
import z`` / ``import apex.x.test_y``, and the relative ``from .test_y import z``
/ ``from . import test_y`` forms a colocated test can use), unless the pair is
in the frozen ``_BASELINE`` of pre-existing debt.

Scope (A-123): the glob used to be ``tests/*.py`` only, so the 137 colocated
``test_*.py`` files under habitat/salis/apex_core/logistay escaped the ratchet
entirely — and 4 of them already violated it undetected. The scan is now
app-wide, so a test relocated out of ``apex/tests/`` carries the ratchet with it
instead of silently leaving it.

The baseline is EMPTY (P-135 retired all 44 pairs — every shared helper and the
base ``ApexHabitatTestCase`` were promoted into ``tests/factories.py``). The
ratchet is therefore absolute: ANY import of a ``test_*`` module from another
test file fails. Put the shared fixture in ``tests/factories.py`` (a
non-``test_*`` module) instead of importing from a sibling test module.
"""

import ast
import glob
import os
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
# App root (``apex/``) — the widened scan walks every module, not just tests/.
_APP_ROOT = os.path.dirname(_TESTS_DIR)

# [#3d5i52]
_BASELINE = frozenset()

# [#ndtaep]
_MUST_BE_CLEAN = frozenset(
    {
        # [#7kg0qw]
        "test_driver_gps_eta.py",
        "test_masar_worker_movement.py",
        "test_driver_portal_attendance.py",
        "test_driver_portal_enrich.py",
        "test_driver_portal_flag.py",
        "test_driver_portal_push.py",
        "test_driver_portal_today.py",
        "test_salis_controls.py",
        # [#g96emv]
        "test_material_transfer.py",
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
        # [#8qn63i]
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


def _is_test_module(dotted):
    """True if a dotted module path's FINAL segment is a ``test_*`` module.

    Generalises the old hardcoded ``apex.tests.test_`` prefix: once tests live
    beside their unit, the offending import is ``apex.habitat.doctype.x.test_x``,
    which that prefix never matched."""
    return bool(dotted) and dotted.rsplit(".", 1)[-1].startswith("test_")


def _test_files():
    """Every ``test_*.py`` anywhere under ``apex/`` — central AND colocated."""
    out = []
    for path in sorted(
        glob.glob(os.path.join(_APP_ROOT, "**", "test_*.py"), recursive=True)
    ):
        if "node_modules" in path:
            continue
        out.append(path)
    # tests/*.py non-test_ helpers (factories.py, _helpers.py) are legitimate
    # shared homes and are never scanned as offenders — only as import targets.
    return out


def _scan():
    """Return the set of (relpath, imported_test_module) pairs, app-wide."""
    found = set()
    for path in _test_files():
        rel = os.path.relpath(path, _APP_ROOT)
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level and not node.module:
                    # `from . import test_sibling`
                    for alias in node.names:
                        if alias.name.startswith("test_"):
                            found.add((rel, "." * node.level + alias.name))
                elif _is_test_module(node.module):
                    # `from apex.x.test_y import z` / `from .test_y import z`
                    found.add((rel, "." * node.level + node.module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_test_module(alias.name):
                        found.add((rel, alias.name))
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
        # _MUST_BE_CLEAN is keyed by bare basename (the P-129 files all lived in
        # tests/); match on basename so it keeps holding after a relocation.
        offenders = sorted(
            (f, m) for (f, m) in _scan() if os.path.basename(f) in _MUST_BE_CLEAN
        )
        self.assertEqual(
            offenders,
            [],
            "A P-129-cleaned file re-introduced a cross-test-module import:\n"
            + "\n".join(f"  {f} -> {m}" for f, m in offenders),
        )


if __name__ == "__main__":
    unittest.main()
