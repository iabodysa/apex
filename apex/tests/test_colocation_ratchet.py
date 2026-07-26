# Copyright (c) 2026, AFMCO and contributors
"""Release-hygiene guard (A-123): the CENTRAL test directory may only shrink.

A-108 shipped its coverage-guard half but never built the ratchet clause it
promised, so nothing stopped ``apex/tests/`` from growing — and it did (175 at
the A-037 merge, 191 today). Meanwhile A-037 had moved 30 test modules the
OPPOSITE way, out of ``api``/``utils`` and INTO ``apex/tests/``, on the premise
that Frappe only discovers tests under ``tests/`` or ``doctype/`` folders. That
premise is FALSE: ``frappe/test_runner.py:149`` os.walks the ENTIRE app path and
line 160 collects any ``test_*.py`` it finds, pruning only ``locals``, ``.git``,
``public`` and ``__pycache__``. A test is discovered wherever it sits — with ONE
exception, the app root itself.

A-196: a ``test_*.py`` sitting DIRECTLY at ``apex/`` runs nothing. ``_add_test``
computes ``relative_path = os.path.relpath(path, app_path)``
(``test_runner.py:305``), which is ``"."`` at the app root, so line 307 sets
``module_name`` to the app PACKAGE ``"apex"``, line 313 imports that package, and
line 330's ``loadTestsFromModule`` finds no TestCase in it — measured zero, for
every app-root file, each one shadowing the last. Two files sat there carrying 20
live methods that had never executed; ``_colocated_tests()`` counted the app root
as a valid colocated home, which is what blessed them. It no longer does, and
``test_no_test_module_at_the_app_root`` now fails outright on any new one.

This guard makes the direction one-way. ``_BASELINE`` freezes the central
inventory; a test file may LEAVE ``apex/tests/`` freely, but a NEW central
``test_*.py`` that is not already in the baseline fails. New tests belong beside
the module they exercise.

A-131 drained the directory: 158 modules moved out to the api / doctype /
report / tasks / utils / seeder / patch / www unit each one exercises, and each
drained name was PRUNED from ``_BASELINE`` as it left. Pruning is what keeps the
ratchet honest — a drained entry left behind would silently buy headroom for a
future central test nobody reviewed.

A-197 closed the two ways that headroom could be BOUGHT rather than earned:

  * The allowance used to be ``len(_BASELINE) + len(_CENTRAL_BY_NECESSITY)``,
    which a padded set raises along with itself — one invented name in EITHER
    set bought exactly one new central test. Proven: adding
    ``test_fuel_request_unified.py`` (a real file, but at ``salis/``, never
    central) to ``_BASELINE`` plus a new ``tests/test_fuel_request_unified.py``
    left all five assertions green one file above the ceiling. The allowance is
    now ``min(_CEILING, ...)`` against a frozen number that padding cannot move.
  * The phantom check resolved a baseline entry against any same-named file
    ANYWHERE under ``apex/``, so borrowing an existing colocated test's NAME
    made an invented entry look like a legitimate drain. A baseline entry must
    now be the central file it names — if it drained it must be pruned, not
    re-resolved somewhere else — and no entry may name two homes at once.

Genuinely app-wide guards (release hygiene, schema integrity, translation
coverage, this file) have no single module to sit beside and stay central
forever — they simply remain baseline entries that never drain. What is left is
that set plus a handful of cross-module suites whose invariant spans two or more
unrelated units, so no single directory is the honest home.

``apex/www`` IS an importable home (A-152): ``apex/www/__init__.py`` now exists,
matching the empty one frappe, erpnext and hrms each ship. It changes no routing —
route discovery allowlists only html/xml/js/css/md (``frappe/website/router.py:117``)
and ``TemplatePage.can_render()`` refuses any Python suffix
(``frappe/website/page_renderers/template_page.py:74``), so neither ``__init__.py``
nor a colocated ``test_*.py`` can be served as a page. Discovery already worked via
PEP 420, so the marker is for tooling, not the runner.

NOTE: this module must not import from a sibling ``test_*`` module (see
test_no_cross_test_imports.py) — it is deliberately stdlib-only.
"""

import glob
import os
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_TESTS_DIR)

# [#a123r1] Frozen 2026-07-25, drained by A-131. This set may only ever SHRINK.
_BASELINE = frozenset(
    {
        "test_b5_role_workspaces.py",
        "test_bed_booking_concurrency.py",
        "test_change_log_popup.py",
        "test_changelog_readme.py",
        "test_colocation_ratchet.py",
        "test_driver_portal_csrf.py",
        "test_duplicate_and_dead_code_guard.py",
        "test_financial_side_effects.py",
        "test_fixture_identifier_entropy.py",
        "test_fleet_number_cards.py",
        "test_fleet_ops_render.py",
        "test_fresh_install_defaults.py",
        "test_front_desk_rate_limit.py",
        "test_housing_lifecycle.py",
        "test_http_enforcement.py",
        "test_internal_auditor_docperms.py",
        "test_log_clearing.py",
        "test_no_cross_test_imports.py",
        "test_onboarding_steps.py",
        "test_permission_parity.py",
        "test_portal_token_security.py",
        "test_qa_probe_systems.py",
        "test_qa_probe_transactions.py",
        "test_release_hygiene.py",
        "test_report_scope.py",
        "test_request_trip_notifications.py",
        "test_schema_integrity.py",
        "test_sql_interpolation_guard.py",
        "test_submittable_controllers.py",
        "test_translation_coverage.py",
        "test_unit_test_coverage_guard.py",
        "test_utils.py",
        "test_worker_party.py",
        "test_workflow_state_governance.py",
        "test_workspace_visibility.py",
    }
)

# [#a123r2] [#a152r1] Guards added after the baseline froze that have no colocated
# home. _BASELINE stays shrink-only; this is the documented escape hatch, and adding
# to it is a review decision, not a way to make room for an ordinary test. See the
# module docstring for why "apex/www is not importable" is no longer a valid reason.
_CENTRAL_BY_NECESSITY = frozenset(
    {
        # Scans every workspace JSON in the app for a parent chain that hides a
        # persona's only surface — no single module owns the invariant.
        "test_workspace_sidebar_reachability.py",
        # Asserts app-wide that no module still references the retired deduction
        # acknowledgment surface and that exactly one module raises an advance.
        "test_native_recovery_surface.py",
        # Drives scripts/comment_audit.py and scripts/check_translations.py as
        # subprocesses; they live outside the apex package and own no module.
        "test_repo_gates.py",
        # Scans every workspace JSON for name/title/parent_page agreement.
        "test_workspace_identity_consistency.py",
        # Reconciles every patch module on disk against patches.txt as a whole;
        # it belongs to the register, not to any one patch.
        "test_patch_registration_guard.py",
        # Walks every shipped record folder in the app checking directory-name and
        # record-name parity; it belongs to the export layout, not to one record.
        "test_standard_record_path_parity.py",
        # Reconciles the hooks apps-screen tile list against the gate helpers spread
        # across apex/www; it spans hooks and five modules, so it owns no single one.
        "test_apps_screen_gate_wiring.py",
        # Compares the served shells, the bundle-guard matrix and the e2e smoke list
        # against each other; the invariant lives between them, not in any one.
        "test_portal_route_coverage.py",
        # Checks every role named in any workspace grant against every DocPerm in the
        # app; the invariant spans both trees, so no single module owns it.
        "test_workspace_role_docperm_guard.py",
        # Ties the published workspace tables to the shipped workspace JSON; it sits
        # between docs/ and the app, and belongs to neither.
        "test_workspace_doc_parity.py",
        # Scans every shipped DocType field description for a translation row.
        "test_schema_description_translation.py",
        # [#a196c1] Reconciles every modules.txt line against every shipped record
        # and every module package at once; like the patches.txt guard above it
        # belongs to the root-level register, not to any one module. Admitted by
        # A-196 to rescue it from the app root, where it collected zero tests —
        # a relocation of an existing guard, not new headroom for a new one.
        "test_declared_modules_are_alive.py",
    }
)

# [#a197c1] The ratchet's HARD ceiling, frozen 2026-07-26 at the count the two
# sets above sum to. It exists because deriving the allowance from those two
# lengths let a padded set buy its own headroom: one invented name raised the
# allowance by exactly one. A frozen integer cannot be moved by padding. It may
# only ever be LOWERED, in the same commit that drains an entry — see
# test_central_test_count_never_grows, which fails if it drifts above the sum.
_CEILING = 47


def _central_tests():
    """Basenames of every ``test_*.py`` directly under ``apex/tests/``."""
    return {
        os.path.basename(p)
        for p in glob.glob(os.path.join(_TESTS_DIR, "test_*.py"))
    }


def _app_root_tests():
    """Basenames of every ``test_*.py`` sitting DIRECTLY at ``apex/``.

    Frappe collects zero tests from each of them (module docstring, A-196), so this
    set must always be empty — it is a stranded-file scan, not an inventory.
    """
    return {os.path.basename(p) for p in glob.glob(os.path.join(_APP_ROOT, "test_*.py"))}


def _colocated_tests():
    """Every ``test_*.py`` under ``apex/`` that has a real package home.

    Excludes ``apex/tests/`` (central) and the app root itself: the root is not a
    home, it is where a test goes to never run.
    """
    out = set()
    for p in glob.glob(os.path.join(_APP_ROOT, "**", "test_*.py"), recursive=True):
        if "node_modules" in p:
            continue
        if os.path.dirname(os.path.abspath(p)) in (_TESTS_DIR, _APP_ROOT):
            continue
        out.add(os.path.relpath(p, _APP_ROOT))
    return out


class TestColocationRatchet(unittest.TestCase):
    def test_no_new_central_test_module(self):
        """A new test must be colocated with the module it exercises."""
        added = sorted(_central_tests() - _BASELINE - _CENTRAL_BY_NECESSITY)
        self.assertEqual(
            added,
            [],
            "New test module(s) added to the central apex/tests/ directory. "
            "Frappe discovers tests anywhere under the app "
            "(frappe/test_runner.py:149 os.walks the whole app path), so a new "
            "test belongs NEXT TO the module it exercises, not here:\n"
            + "\n".join(f"  apex/tests/{f}" for f in added),
        )

    def test_no_test_module_at_the_app_root(self):
        """A ``test_*.py`` directly at ``apex/`` executes NOTHING (A-196)."""
        stranded = sorted(_app_root_tests())
        self.assertEqual(
            stranded,
            [],
            "test module(s) sitting directly at apex/. Frappe walks the file but "
            "imports it as the app PACKAGE — frappe/test_runner.py:305 makes "
            "relative_path '.' at the app root, line 307 sets module_name to "
            "'apex', and line 330 loads zero tests from it. The file passes review "
            "and silently never runs. Move it into a package: beside the module it "
            "exercises, or apex/tests/ if the invariant is genuinely app-wide:\n"
            + "\n".join(f"  apex/{f}" for f in stranded),
        )

    def test_central_test_count_never_grows(self):
        """The ratchet proper: the central count is monotonically non-increasing."""
        current = len(_central_tests())
        accounted = len(_BASELINE) + len(_CENTRAL_BY_NECESSITY)
        # [#a197c2] The ceiling must stay TIGHT against the sets, or it goes
        # vestigial: a drain that shrinks them while _CEILING stays put would
        # leave the difference as unreviewed headroom. Lower it with the drain.
        self.assertLessEqual(
            _CEILING,
            accounted,
            f"_CEILING ({_CEILING}) now exceeds baseline {len(_BASELINE)} + "
            f"{len(_CENTRAL_BY_NECESSITY)} central-by-necessity = {accounted}. "
            "An entry drained without the ceiling following it down — lower "
            f"_CEILING to {accounted}, or the gap is free headroom.",
        )
        # [#a197c3] min(), never the sum alone: padding either set raises
        # `accounted` but cannot move the frozen ceiling, so it buys no headroom.
        allowed = min(_CEILING, accounted)
        self.assertLessEqual(
            current,
            allowed,
            f"apex/tests/ grew to {current} test modules (allowed {allowed} = "
            f"min(ceiling {_CEILING}, baseline {len(_BASELINE)} + "
            f"{len(_CENTRAL_BY_NECESSITY)} central-by-necessity)). "
            "The central directory may only shrink — relocate tests out to their "
            "module, never add new ones in.",
        )

    def test_baseline_has_no_phantom_entries(self):
        """Hygiene: every baseline entry must BE the central file it names.

        [#a197c4] This used to accept an entry that matched any same-named file
        ANYWHERE under apex/, on the theory that a drained entry "reappears" as
        a colocated test. That resolved a drained name against a file it never
        left from, so padding _BASELINE with the basename of any existing
        colocated test passed as a legitimate drain and widened the ratchet.
        A drained entry is PRUNED (module docstring), never re-resolved — so the
        only file a baseline entry may resolve to is apex/tests/<name> itself.
        """
        central = _central_tests()
        phantom = sorted(n for n in _BASELINE if n not in central)
        self.assertEqual(
            phantom,
            [],
            "Baseline entr(ies) name no file in apex/tests/. A drained entry is "
            "pruned from _BASELINE as it leaves — it must NOT be left behind to "
            "resolve against a same-named file elsewhere in the tree, which "
            "silently widens the ratchet:\n" + "\n".join(f"  {n}" for n in phantom),
        )

    def test_no_accounted_name_claims_two_homes(self):
        """[#a197c5] An accounted central name may not also exist colocated.

        The ratchet's contract is that a name is central until it drains, and
        that draining deletes the central copy and prunes the entry — so the two
        homes are mutually exclusive. A name living in both is the signature of
        an entry padded by BORROWING an existing colocated test's identity to
        make an invented central file look already-accounted-for.

        Zero occurrences today (verified across all 47 central and 313 colocated
        modules). If a colocated test ever legitimately wants a central guard's
        basename, rename it or drain the central one — either is a review event,
        which is the point.
        """
        colocated = {os.path.basename(p): p for p in sorted(_colocated_tests())}
        accounted = _BASELINE | _CENTRAL_BY_NECESSITY
        both = sorted(n for n in accounted & _central_tests() if n in colocated)
        self.assertEqual(
            both,
            [],
            "Accounted central name(s) ALSO exist as a colocated test. Either a "
            "drain left its central copy behind, or an entry was padded with an "
            "existing colocated name to buy headroom:\n"
            + "\n".join(f"  apex/tests/{n}  vs  apex/{colocated[n]}" for n in both),
        )

    def test_central_by_necessity_entries_all_exist(self):
        """The escape hatch may not be padded with names that match no file.

        Same anti-padding rule as the baseline: an entry that has been relocated
        or deleted must be pruned, or it silently buys room for a future central
        test that nobody reviewed."""
        stale = sorted(_CENTRAL_BY_NECESSITY - _central_tests())
        self.assertEqual(
            stale,
            [],
            "Central-by-necessity entr(ies) match no file under apex/tests/. "
            "Prune them instead of leaving room the ratchet cannot account for:\n"
            + "\n".join(f"  {n}" for n in stale),
        )

    def test_guard_actually_detects(self):
        """Guard-of-the-guard: prove the scan is not silently empty.

        [#a131g1] The central floor was 50, calibrated when the directory still
        held ~190 modules. A-131 drained it to the app-wide guards, so that
        number had become an assertion about the OLD inventory size rather than
        about the scan working — it fails on a successful drain. The floor is
        now 10, which still catches a scan that silently returns nothing (a
        broken glob, a moved _TESTS_DIR) without re-encoding an inventory count
        that this very card exists to shrink. The colocated floor keeps its 50:
        that side only grows.
        """
        central = _central_tests()
        self.assertGreater(len(central), 10, "central scan returned implausibly few files")
        self.assertGreater(
            len(_colocated_tests()), 50, "colocated scan returned implausibly few files"
        )
        self.assertIn(os.path.basename(__file__), central)
        # A name that is not in the baseline must be reported as an addition.
        self.assertNotIn("test_definitely_not_a_real_module_a123.py", _BASELINE)
        # [#a196g1] The app-root scan asserts an EMPTY set, so it would also pass
        # against a _APP_ROOT pointing nowhere. Prove the directory it globs is
        # really the app root before believing that emptiness.
        for marker in ("modules.txt", "hooks.py", "setup.py"):
            self.assertTrue(
                os.path.exists(os.path.join(_APP_ROOT, marker)),
                f"_APP_ROOT is not the app root — {marker} missing, app-root scan is blind",
            )


if __name__ == "__main__":
    unittest.main()
