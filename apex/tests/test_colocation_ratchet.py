# Copyright (c) 2026, AFMCO and contributors
"""Release-hygiene guard (A-123): the CENTRAL test directory may only shrink.

A-108 shipped its coverage-guard half but never built the ratchet clause it
promised, so nothing stopped ``apex/tests/`` from growing — and it did (175 at
the A-037 merge, 191 today). Meanwhile A-037 had moved 30 test modules the
OPPOSITE way, out of ``api``/``utils`` and INTO ``apex/tests/``, on the premise
that Frappe only discovers tests under ``tests/`` or ``doctype/`` folders. That
premise is FALSE: ``frappe/test_runner.py:149`` os.walks the ENTIRE app path and
line 160 collects any ``test_*.py`` it finds, pruning only ``locals``, ``.git``,
``public`` and ``__pycache__``. A test is discovered wherever it sits.

This guard makes the direction one-way. ``_BASELINE`` freezes the central
inventory as of 2026-07-25; a test file may LEAVE ``apex/tests/`` freely (that
is the 104-file relocation, carried by its own card), but a NEW central
``test_*.py`` that is not already in the baseline fails. New tests belong beside
the module they exercise.

Genuinely app-wide guards (release hygiene, schema integrity, translation
coverage, this file) have no single module to sit beside and stay central
forever — they simply remain baseline entries that never drain.

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

# [#a123r1] Frozen 2026-07-25. This set may only ever SHRINK.
_BASELINE = frozenset(
    {
        "test_b5_role_workspaces.py",
        "test_backfill_assignment_facility_supervisor.py",
        "test_bed_booking_concurrency.py",
        "test_building_address_backfill.py",
        "test_change_log_popup.py",
        "test_changelog_readme.py",
        "test_colocation_ratchet.py",
        "test_driver_portal_csrf.py",
        "test_duplicate_and_dead_code_guard.py",
        "test_financial_side_effects.py",
        "test_fixture_identifier_entropy.py",
        "test_fleet_alert_notifications.py",
        "test_fleet_number_cards.py",
        "test_fleet_ops_render.py",
        "test_fleet_page_access_gate.py",
        "test_fresh_install_defaults.py",
        "test_front_desk_rate_limit.py",
        "test_habitat_expiry_notifications.py",
        "test_housing_count_page_access_gate.py",
        "test_housing_lifecycle.py",
        "test_http_enforcement.py",
        "test_internal_auditor_docperms.py",
        "test_log_clearing.py",
        "test_masar_1b.py",
        "test_masar_supervisor_page_access_gate.py",
        "test_no_cross_test_imports.py",
        "test_onboarding_steps.py",
        "test_permission_parity.py",
        "test_portal_csrf_bootstrap.py",
        "test_portal_token_security.py",
        "test_portal_xss.py",
        "test_qa_probe_systems.py",
        "test_qa_probe_transactions.py",
        "test_release_hygiene.py",
        "test_reorder_root_workspace.py",
        "test_report_scope.py",
        "test_request_trip_notifications.py",
        "test_safety_page_access_gate.py",
        "test_schema_integrity.py",
        "test_seed_demo_role_logins_gate.py",
        "test_seed_masar_demo_movement_gate.py",
        "test_setup_roles.py",
        "test_sim_actions.py",
        "test_sim_contract_billing.py",
        "test_sim_migration.py",
        "test_sim_operations_scoping.py",
        "test_sim_reports.py",
        "test_sim_telecom_control.py",
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
        # Scans the whole apex/www tree for external CDN hosts. DRAINABLE since
        # A-152 made apex/www a package; kept central only until a follow-up
        # moves it, and it may never be cited as an importability blocker.
        "test_www_no_external_cdn_assets.py",
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
    }
)


def _central_tests():
    """Basenames of every ``test_*.py`` directly under ``apex/tests/``."""
    return {
        os.path.basename(p)
        for p in glob.glob(os.path.join(_TESTS_DIR, "test_*.py"))
    }


def _colocated_tests():
    """Every ``test_*.py`` anywhere under ``apex/`` EXCEPT ``apex/tests/``."""
    out = set()
    for p in glob.glob(os.path.join(_APP_ROOT, "**", "test_*.py"), recursive=True):
        if "node_modules" in p:
            continue
        if os.path.dirname(os.path.abspath(p)) == _TESTS_DIR:
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

    def test_central_test_count_never_grows(self):
        """The ratchet proper: the central count is monotonically non-increasing."""
        current = len(_central_tests())
        allowed = len(_BASELINE) + len(_CENTRAL_BY_NECESSITY)
        self.assertLessEqual(
            current,
            allowed,
            f"apex/tests/ grew to {current} test modules (baseline "
            f"{len(_BASELINE)} + {len(_CENTRAL_BY_NECESSITY)} central-by-necessity). "
            "The central directory may only shrink — relocate tests out to their "
            "module, never add new ones in.",
        )

    def test_baseline_has_no_phantom_entries(self):
        """Hygiene: the baseline must never gain a name that was never central.

        Guards the ratchet against being 'fixed' by padding _BASELINE with
        invented names to make room for a new central test. Every baseline
        entry must either still exist centrally, or exist as a colocated file
        (i.e. it drained legitimately)."""
        colocated_basenames = {os.path.basename(p) for p in _colocated_tests()}
        central = _central_tests()
        phantom = sorted(
            n for n in _BASELINE if n not in central and n not in colocated_basenames
        )
        self.assertEqual(
            phantom,
            [],
            "Baseline entr(ies) match no file anywhere — a drained entry should "
            "reappear as a colocated test. Prune it from _BASELINE instead of "
            "leaving a phantom that silently widens the ratchet:\n"
            + "\n".join(f"  {n}" for n in phantom),
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
        """Guard-of-the-guard: prove the scan is not silently empty."""
        central = _central_tests()
        self.assertGreater(len(central), 50, "central scan returned implausibly few files")
        self.assertGreater(
            len(_colocated_tests()), 50, "colocated scan returned implausibly few files"
        )
        self.assertIn(os.path.basename(__file__), central)
        # A name that is not in the baseline must be reported as an addition.
        self.assertNotIn("test_definitely_not_a_real_module_a123.py", _BASELINE)


if __name__ == "__main__":
    unittest.main()
