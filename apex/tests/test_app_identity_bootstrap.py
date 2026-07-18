"""Tests for the temporary legacy app identity bootstrap."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apex_habitat import bootstrap, hooks
from apex_habitat.bootstrap import IdentityCutoverError, canonicalize_installed_apps
from apex.patches.v2_0 import rename_app_apex_habitat_to_apex as rename_patch


class TestCanonicalizeInstalledApps(unittest.TestCase):
	def test_maps_legacy_identity_and_deduplicates_at_first_occurrence(self):
		installed_apps = json.dumps(
			["frappe", "apex_habitat", "erpnext", "apex", "hrms"]
		)

		self.assertEqual(
			canonicalize_installed_apps(installed_apps),
			["frappe", "apex", "erpnext", "hrms"],
		)

	def test_canonical_identity_before_legacy_keeps_canonical_position(self):
		installed_apps = json.dumps(["frappe", "apex", "erpnext", "apex_habitat"])

		self.assertEqual(
			canonicalize_installed_apps(installed_apps),
			["frappe", "apex", "erpnext"],
		)

	def test_canonical_only_state_is_idempotent(self):
		installed_apps = ["frappe", "erpnext", "apex", "hrms"]

		self.assertEqual(
			canonicalize_installed_apps(json.dumps(installed_apps)),
			installed_apps,
		)

	def test_malformed_json_raises_actionable_error(self):
		with self.assertRaisesRegex(IdentityCutoverError, "valid JSON"):
			canonicalize_installed_apps('["frappe",')

	def test_non_list_or_non_string_items_raise_actionable_error(self):
		for installed_apps in ({"apex": True}, ["frappe", 7, "apex_habitat"]):
			with self.subTest(installed_apps=installed_apps):
				with self.assertRaisesRegex(IdentityCutoverError, "JSON list"):
					canonicalize_installed_apps(json.dumps(installed_apps))

	def test_state_with_neither_identity_raises_actionable_error(self):
		with self.assertRaisesRegex(IdentityCutoverError, "neither"):
			canonicalize_installed_apps(json.dumps(["frappe", "erpnext", "hrms"]))


class TestBeforeMigrate(unittest.TestCase):
	def _frappe(self, installed_apps, request_cache=None):
		db = SimpleNamespace(
			get_global=MagicMock(return_value=installed_apps),
			set_global=MagicMock(),
		)
		cache = SimpleNamespace(delete_value=MagicMock())
		local = SimpleNamespace(request_cache=request_cache or {"sentinel": object()})
		return SimpleNamespace(db=db, cache=cache, local=local)

	def test_rewrites_legacy_state_and_clears_app_caches(self):
		frappe = self._frappe(
			json.dumps(["frappe", "apex_habitat", "erpnext", "hrms"])
		)

		with patch.object(bootstrap, "frappe", frappe):
			bootstrap.before_migrate()

		frappe.db.get_global.assert_called_once_with("installed_apps")
		frappe.db.set_global.assert_called_once_with(
			"installed_apps", json.dumps(["frappe", "apex", "erpnext", "hrms"])
		)
		frappe.cache.delete_value.assert_called_once_with(["app_hooks", "all_apps"])
		self.assertEqual(frappe.local.request_cache, {})

	def test_canonical_state_does_not_write_or_clear_caches(self):
		request_cache = {"sentinel": object()}
		frappe = self._frappe(
			json.dumps(["frappe", "apex", "erpnext", "hrms"]),
			request_cache=request_cache,
		)

		with patch.object(bootstrap, "frappe", frappe):
			bootstrap.before_migrate()

		frappe.db.set_global.assert_not_called()
		frappe.cache.delete_value.assert_not_called()
		self.assertIs(frappe.local.request_cache, request_cache)
		self.assertIn("sentinel", request_cache)

	def test_changed_state_tolerates_missing_request_cache(self):
		frappe = self._frappe(json.dumps(["apex_habitat"]))
		frappe.local = SimpleNamespace()

		with patch.object(bootstrap, "frappe", frappe):
			bootstrap.before_migrate()

		frappe.db.set_global.assert_called_once_with("installed_apps", json.dumps(["apex"]))


class TestRewriteBenchAppsRegistry(unittest.TestCase):
	def test_replaces_exact_legacy_line_and_preserves_other_bytes(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			apps_path = Path(temp_dir) / "apps.txt"
			apps_path.write_bytes(b"frappe\r\napex_habitat\nhrms\r")

			changed = bootstrap.rewrite_bench_apps_registry(apps_path)

			self.assertTrue(changed)
			self.assertEqual(apps_path.read_bytes(), b"frappe\r\napex\nhrms\r")

	def test_preserves_original_file_mode(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			apps_path = Path(temp_dir) / "apps.txt"
			apps_path.write_text("frappe\napex_habitat\n", encoding="utf-8")
			os.chmod(apps_path, 0o640)

			bootstrap.rewrite_bench_apps_registry(apps_path)

			self.assertEqual(apps_path.stat().st_mode & 0o777, 0o640)

	def test_canonical_only_state_is_a_no_op(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			apps_path = Path(temp_dir) / "apps.txt"
			original = b"frappe\napex\nhrms\n"
			apps_path.write_bytes(original)

			with patch.object(bootstrap.os, "replace") as replace:
				changed = bootstrap.rewrite_bench_apps_registry(apps_path)

			self.assertFalse(changed)
			replace.assert_not_called()
			self.assertEqual(apps_path.read_bytes(), original)

	def test_ambiguous_identity_states_fail_closed(self):
		states = {
			"mixed": "frappe\napex_habitat\napex\n",
			"missing_exact_identity": "frappe\napex_habitat \nhrms\n",
			"duplicate_legacy": "apex_habitat\nfrappe\napex_habitat\n",
		}
		for name, content in states.items():
			with self.subTest(name=name):
				with tempfile.TemporaryDirectory() as temp_dir:
					apps_path = Path(temp_dir) / "apps.txt"
					apps_path.write_text(content, encoding="utf-8")

					with self.assertRaisesRegex(IdentityCutoverError, "ambiguous"):
						bootstrap.rewrite_bench_apps_registry(apps_path)

					self.assertEqual(apps_path.read_text(encoding="utf-8"), content)

	def test_failed_replace_preserves_original_and_removes_temp_file(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			root = Path(temp_dir)
			apps_path = root / "apps.txt"
			original = b"frappe\napex_habitat\n"
			apps_path.write_bytes(original)

			with patch.object(bootstrap.os, "replace", side_effect=OSError("replace failed")):
				with self.assertRaisesRegex(OSError, "replace failed"):
					bootstrap.rewrite_bench_apps_registry(apps_path)

			self.assertEqual(apps_path.read_bytes(), original)
			self.assertEqual({entry.name for entry in root.iterdir()}, {"apps.txt"})


class TestRenameAppIdentityPatch(unittest.TestCase):
	def test_registry_rewrite_invalidates_app_and_request_caches(self):
		request_cache = {"sentinel": object()}
		frappe = SimpleNamespace(
			cache=SimpleNamespace(delete_value=MagicMock()),
			local=SimpleNamespace(
				sites_path="/srv/frappe/sites",
				request_cache=request_cache,
			),
		)

		with (
			patch.object(rename_patch, "frappe", frappe),
			patch.object(
				rename_patch, "rewrite_bench_apps_registry", return_value=True
			) as rewrite_registry,
		):
			rename_patch._rename_bench_apps_registry()

		rewrite_registry.assert_called_once_with(Path("/srv/frappe/sites") / "apps.txt")
		frappe.cache.delete_value.assert_called_once_with(["app_hooks", "all_apps"])
		self.assertEqual(request_cache, {})

	def test_registry_no_op_keeps_caches(self):
		request_cache = {"sentinel": object()}
		frappe = SimpleNamespace(
			cache=SimpleNamespace(delete_value=MagicMock()),
			local=SimpleNamespace(
				sites_path="/srv/frappe/sites",
				request_cache=request_cache,
			),
		)

		with (
			patch.object(rename_patch, "frappe", frappe),
			patch.object(
				rename_patch, "rewrite_bench_apps_registry", return_value=False
			),
		):
			rename_patch._rename_bench_apps_registry()

		frappe.cache.delete_value.assert_not_called()
		self.assertIn("sentinel", request_cache)

	def test_execute_repairs_registry_before_database_rewrites(self):
		call_order = []
		helper_names = (
			"_rename_bench_apps_registry",
			"_rewrite_dotted_paths",
			"_rename_module_def",
			"_rename_installed_application_rows",
			"_rename_installed_apps_global",
		)

		patchers = [
			patch.object(
				rename_patch,
				name,
				side_effect=lambda name=name: call_order.append(name),
			)
			for name in helper_names
		]
		for helper_patcher in patchers:
			self.enterContext(helper_patcher)

		rename_patch.execute()

		self.assertEqual(call_order, list(helper_names))


class TestLegacyHooks(unittest.TestCase):
	def test_exposes_only_before_migrate_hook(self):
		self.assertEqual(
			hooks.before_migrate,
			["apex_habitat.bootstrap.before_migrate"],
		)
		public_names = {name for name in vars(hooks) if not name.startswith("_")}
		self.assertEqual(public_names, {"before_migrate"})

	def test_does_not_expose_business_hooks(self):
		for hook_name in (
			"doc_events",
			"override_doctype_class",
			"scheduler_events",
			"permission_query_conditions",
			"has_permission",
			"auth_hooks",
		):
			with self.subTest(hook_name=hook_name):
				self.assertFalse(hasattr(hooks, hook_name))


if __name__ == "__main__":
	unittest.main()
