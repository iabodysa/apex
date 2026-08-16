# Copyright (c) 2026, AFMCO and contributors
"""Release-hygiene guard: no NEW cross-test-module imports.

A test module must NOT import fixture helpers from a sibling ``test_*`` module —
shared builders belong in ``tests/factories.py``. This guard AST-scans every
``test_*.py`` ANYWHERE under ``apex/`` and fails on any import whose target
module's final segment starts with ``test_`` (absolute ``from apex.x.test_y
import z`` / ``import apex.x.test_y``, and the relative ``from .test_y import z``
/ ``from . import test_y`` forms a colocated test can use), unless the pair is
in the frozen ``_BASELINE`` of pre-existing debt.

Scope: the glob covered ``tests/*.py`` only, so the 137 colocated
``test_*.py`` files under habitat/salis/apex_core/logistay escaped the ratchet
entirely — and 4 of them already violated it undetected. The scan is now
app-wide, so a test relocated out of ``apex/tests/`` carries the ratchet with it
instead of silently leaving it.

Importer scope: the offender scan iterated ``test_*.py`` only, so
the ban was launderable in one hop. ``tests/`` legitimately holds non-``test_``
modules — ``factories.py``, ``_helpers.py``, ``workspace_reachability.py`` — and a
new one could ``from .test_x import helper`` and re-export it; every ``test_*``
module then imports the shim, no ``test_*`` module imports a ``test_*`` module, and
the ratchet reports clean while the coupling it exists to prevent is fully restored.
The scan now treats EVERY ``.py`` under ``apex/`` as a possible importer. That is
strictly stronger than closing the ``tests/``-helper hole alone and costs nothing:
importing a test module is never legitimate from anywhere, production included, and
the app-wide sweep finds 0 offenders today — so the baseline stays empty.

The baseline is EMPTY (all 44 pairs are retired — every shared helper and the
base ``ApexHabitatTestCase`` were promoted into ``tests/factories.py``). The
ratchet is therefore absolute: ANY import of a ``test_*`` module from any other
module fails. Put the shared fixture in ``tests/factories.py`` (a non-``test_*``
module) instead of importing from a sibling test module.
"""

import ast
import glob
import os
import unittest

from apex.tests.source_tree import APP_ROOT as _APP_ROOT
from apex.tests.source_tree import SUITE_PACKAGE as _SUITE_PACKAGE

# The naive anchor ``dirname(dirname(__file__))`` resolves relative to this file, so
# once the suite moved off the app package it named ``.claude/tests/apex`` — the
# mirror, a tree holding nothing but test modules — while a stale comment above it
# still claimed ``apex/``. That left the guard blind to every PRODUCTION module: its
# offender universe was the mirror alone. Anchoring on ``source_tree.APP_ROOT``
# (``apex.__file__``) restores the intended population, and the mirror is scanned
# too — the suite's own modules are equally forbidden to import a sibling ``test_*``.

_BASELINE = frozenset()

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


def _importer_files():
    """Every ``.py`` anywhere under ``apex/`` — the offender universe.

    Deliberately NOT just ``test_*.py``: a non-``test_`` module (a new
    ``tests/`` helper, or any production module) importing a ``test_*`` module is
    the laundering path this guard exists to close, and it is never legitimate
    from any file, so the widest possible importer set is also the correct one."""
    out = []
    for root in (_APP_ROOT, _SUITE_PACKAGE):
        for path in sorted(glob.glob(os.path.join(root, "**", "*.py"), recursive=True)):
            if "node_modules" in path or "__pycache__" in path:
                continue
            out.append(path)
    return out


def _rel(path):
    """``path`` named against whichever root holds it — app first, then the mirror."""
    root = _APP_ROOT if path.startswith(_APP_ROOT) else _SUITE_PACKAGE
    return os.path.relpath(path, root)


def _scan():
    """Return the set of (relpath, imported_test_module) pairs, app-wide."""
    found = set()
    for path in _importer_files():
        rel = _rel(path)
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
    def test_importer_scan_covers_non_test_modules(self):
        # The offender-scan blind spot: the shared non-test_ helpers under tests/
        # are the laundering vector, so they must be in the OFFENDER universe, not
        # only the import-target universe.
        scanned = {_rel(p) for p in _importer_files()}
        for helper in ("factories.py", "_helpers.py", "workspace_reachability.py"):
            rel = os.path.join("tests", helper)
            self.assertTrue(os.path.exists(os.path.join(_APP_ROOT, rel)), f"{rel} moved — update this test")
            self.assertIn(rel, scanned, f"{rel} could launder the ban if left unscanned")
        # Positive control: the offender universe must reach real production code,
        # not only test modules. With the naive anchor this passed on the mirror,
        # where the non-``test_`` files were the mirror's own duplicated helpers.
        self.assertIn("hooks.py", scanned, "offender universe does not reach the app root")
        self.assertTrue(
            any(not os.path.basename(p).startswith("test_") for p in scanned),
            "offender universe must not be limited to test_*.py",
        )

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
        # _MUST_BE_CLEAN is keyed by bare basename (all of these currently live in
        # tests/); match on basename so it keeps holding after a relocation.
        offenders = sorted(
            (f, m) for (f, m) in _scan() if os.path.basename(f) in _MUST_BE_CLEAN
        )
        self.assertEqual(
            offenders,
            [],
            "An already-cleaned file re-introduced a cross-test-module import:\n"
            + "\n".join(f"  {f} -> {m}" for f, m in offenders),
        )


if __name__ == "__main__":
    unittest.main()
