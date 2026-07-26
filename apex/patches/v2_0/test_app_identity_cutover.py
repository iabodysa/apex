# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for the operator-invoked app-identity cutover planning helpers.

No site, no DB, no frappe import: every function under test is pure string,
JSON and table-metadata manipulation, so the cutover logic an operator will run
against a real site is exercised here against fixtures instead.

The site-touching entry points (diagnose / cutover) are deliberately not called;
they only sequence the helpers below and are rehearsed on a scratch site per
docs/UPGRADE-APP-IDENTITY.md.
"""

import unittest

from apex.patches.v2_0 import app_identity_cutover as cutover


class TestClassifyRegistry(unittest.TestCase):
    def test_legacy_registry(self):
        content = "frappe\nerpnext\nhrms\napex_habitat\n"
        self.assertEqual(cutover.classify_registry(content), cutover.REGISTRY_LEGACY)

    def test_canonical_registry(self):
        content = "frappe\nerpnext\nhrms\napex\n"
        self.assertEqual(cutover.classify_registry(content), cutover.REGISTRY_CANONICAL)

    def test_both_identities_is_ambiguous(self):
        content = "frappe\napex_habitat\napex\n"
        self.assertEqual(cutover.classify_registry(content), cutover.REGISTRY_AMBIGUOUS)

    def test_duplicate_legacy_is_ambiguous(self):
        content = "frappe\napex_habitat\napex_habitat\n"
        self.assertEqual(cutover.classify_registry(content), cutover.REGISTRY_AMBIGUOUS)

    def test_neither_identity_is_absent(self):
        self.assertEqual(cutover.classify_registry("frappe\nerpnext\n"), cutover.REGISTRY_ABSENT)

    def test_surrounding_whitespace_does_not_hide_the_identity(self):
        self.assertEqual(cutover.classify_registry("  apex_habitat  \n"), cutover.REGISTRY_LEGACY)

    def test_a_longer_app_name_is_not_the_legacy_identity(self):
        content = "frappe\napex_habitat_extra\napex\n"
        self.assertEqual(cutover.classify_registry(content), cutover.REGISTRY_CANONICAL)


class TestRewriteRegistry(unittest.TestCase):
    def test_rewrites_only_the_identity_line(self):
        content = "frappe\nerpnext\nhrms\napex_habitat\n"
        self.assertEqual(cutover.rewrite_registry(content), "frappe\nerpnext\nhrms\napex\n")

    def test_preserves_crlf_line_endings(self):
        content = "frappe\r\napex_habitat\r\n"
        self.assertEqual(cutover.rewrite_registry(content), "frappe\r\napex\r\n")

    def test_preserves_a_missing_trailing_newline(self):
        self.assertEqual(cutover.rewrite_registry("frappe\napex_habitat"), "frappe\napex")

    def test_canonical_text_round_trips_unchanged(self):
        content = "frappe\nerpnext\napex\n"
        self.assertEqual(cutover.rewrite_registry(content), content)

    def test_rewrite_is_idempotent(self):
        once = cutover.rewrite_registry("frappe\napex_habitat\n")
        self.assertEqual(cutover.rewrite_registry(once), once)

    def test_ambiguous_registry_raises(self):
        with self.assertRaises(cutover.IdentityCutoverError):
            cutover.rewrite_registry("apex_habitat\napex\n")

    def test_registry_without_either_identity_raises(self):
        with self.assertRaises(cutover.IdentityCutoverError):
            cutover.rewrite_registry("frappe\nerpnext\n")


class TestCanonicalizeInstalledApps(unittest.TestCase):
    def test_legacy_identity_becomes_canonical_in_place(self):
        serialized = '["frappe", "erpnext", "apex_habitat", "hrms"]'
        self.assertEqual(
            cutover.canonicalize_installed_apps(serialized),
            ["frappe", "erpnext", "apex", "hrms"],
        )

    def test_mixed_list_collapses_to_one_entry(self):
        serialized = '["frappe", "apex_habitat", "erpnext", "apex"]'
        self.assertEqual(
            cutover.canonicalize_installed_apps(serialized), ["frappe", "apex", "erpnext"]
        )

    def test_already_canonical_list_is_unchanged(self):
        serialized = '["frappe", "erpnext", "apex"]'
        self.assertEqual(
            cutover.canonicalize_installed_apps(serialized), ["frappe", "erpnext", "apex"]
        )

    def test_invalid_json_raises(self):
        with self.assertRaises(cutover.IdentityCutoverError):
            cutover.canonicalize_installed_apps("not json")

    def test_non_list_json_raises(self):
        with self.assertRaises(cutover.IdentityCutoverError):
            cutover.canonicalize_installed_apps('{"apps": ["apex"]}')

    def test_non_string_element_raises(self):
        with self.assertRaises(cutover.IdentityCutoverError):
            cutover.canonicalize_installed_apps('["frappe", 7]')

    def test_list_naming_neither_identity_raises(self):
        with self.assertRaises(cutover.IdentityCutoverError):
            cutover.canonicalize_installed_apps('["frappe", "erpnext"]')


class TestRewriteDotted(unittest.TestCase):
    def test_rewrites_a_stored_method_path(self):
        self.assertEqual(
            cutover.rewrite_dotted("apex_habitat.habitat.api.dashboard.occupancy"),
            "apex.habitat.api.dashboard.occupancy",
        )

    def test_rewrites_every_occurrence_in_one_value(self):
        self.assertEqual(
            cutover.rewrite_dotted("apex_habitat.a and apex_habitat.b"), "apex.a and apex.b"
        )

    def test_bare_token_without_a_dot_is_untouched(self):
        self.assertEqual(cutover.rewrite_dotted("apex_habitat"), "apex_habitat")

    def test_longer_package_name_is_untouched(self):
        self.assertEqual(cutover.rewrite_dotted("apex_habitat_extra.run"), "apex_habitat_extra.run")

    def test_already_canonical_value_is_untouched(self):
        self.assertEqual(cutover.rewrite_dotted("apex.habitat.api.x"), "apex.habitat.api.x")

    def test_empty_and_none_survive(self):
        self.assertEqual(cutover.rewrite_dotted(""), "")
        self.assertIsNone(cutover.rewrite_dotted(None))


class TestIsSafeIdentifier(unittest.TestCase):
    def test_accepts_frappe_table_and_column_names(self):
        self.assertTrue(cutover.is_safe_identifier("tabNumber Card"))
        self.assertTrue(cutover.is_safe_identifier("email_id"))

    def test_rejects_backtick_and_semicolon_and_empty(self):
        self.assertFalse(cutover.is_safe_identifier("tab`Card"))
        self.assertFalse(cutover.is_safe_identifier("x; DROP TABLE y"))
        self.assertFalse(cutover.is_safe_identifier(""))


def _column(table, name, data_type="varchar"):
    return {"table_name": table, "column_name": name, "data_type": data_type}


class TestPlanSweep(unittest.TestCase):
    def test_keeps_a_plain_text_column(self):
        planned = cutover.plan_sweep([_column("tabNumber Card", "method")])
        self.assertEqual(planned, [("tabNumber Card", "method")])

    def test_drops_non_text_types(self):
        columns = [_column("tabX", "qty", "int"), _column("tabX", "rate", "decimal")]
        self.assertEqual(cutover.plan_sweep(columns), [])

    def test_keeps_every_declared_text_type(self):
        columns = [_column("tabX", data_type, data_type) for data_type in cutover.TEXT_TYPES]
        self.assertEqual(len(cutover.plan_sweep(columns)), len(cutover.TEXT_TYPES))

    def test_drops_audit_trail_tables(self):
        columns = [_column(table, "patch") for table in cutover.SWEEP_SKIP_TABLES]
        self.assertEqual(cutover.plan_sweep(columns), [])

    def test_patch_log_is_actually_skipped(self):
        self.assertIn("tabPatch Log", cutover.SWEEP_SKIP_TABLES)
        self.assertEqual(cutover.plan_sweep([_column("tabPatch Log", "patch")]), [])

    def test_drops_non_frappe_tables(self):
        self.assertEqual(cutover.plan_sweep([_column("__global_search", "content")]), [])

    def test_drops_non_identifier_names(self):
        columns = [_column("tab`Card", "method"), _column("tabCard", "me`thod")]
        self.assertEqual(cutover.plan_sweep(columns), [])

    def test_output_is_sorted_and_deduplicated(self):
        columns = [
            _column("tabZ", "b"),
            _column("tabA", "a"),
            _column("tabZ", "b"),
        ]
        self.assertEqual(cutover.plan_sweep(columns), [("tabA", "a"), ("tabZ", "b")])


if __name__ == "__main__":
    unittest.main()
