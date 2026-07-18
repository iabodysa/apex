"""Tests for the temporary legacy app identity bootstrap."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from setuptools import find_packages

from apex import hooks as canonical_hooks
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
	def _frappe(self, installed_apps, sites_path, request_cache=None, legacy_patches=False):
		def sql(query, values=None):
			if query.lstrip().startswith("SELECT"):
				return [("legacy-row",)] if legacy_patches else []
			return None

		db = SimpleNamespace(
			get_global=MagicMock(return_value=installed_apps),
			set_global=MagicMock(),
			sql=MagicMock(side_effect=sql),
		)
		cache = SimpleNamespace(delete_value=MagicMock())
		local = SimpleNamespace(
			sites_path=sites_path,
			request_cache=request_cache
			if request_cache is not None
			else {"sentinel": object()},
			app_modules={"apex_habitat": ["habitat"]},
			module_app={"habitat": "apex_habitat"},
		)
		return SimpleNamespace(
			db=db,
			cache=cache,
			local=local,
			setup_module_map=MagicMock(),
		)

	def test_rewrites_legacy_state_and_clears_app_caches(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			apps_path = Path(temp_dir) / "apps.txt"
			apps_path.write_text("frappe\napex_habitat\n", encoding="utf-8")
			frappe = self._frappe(
				json.dumps(["frappe", "apex_habitat", "erpnext", "hrms"]),
				temp_dir,
			)

			with patch.object(bootstrap, "frappe", frappe):
				bootstrap.before_migrate()
			registry_content = apps_path.read_text(encoding="utf-8")

		frappe.db.get_global.assert_called_once_with("installed_apps")
		frappe.db.set_global.assert_called_once_with(
			"installed_apps", json.dumps(["frappe", "apex", "erpnext", "hrms"])
		)
		frappe.cache.delete_value.assert_called_once_with(
			bootstrap.APP_DISCOVERY_CACHE_KEYS
		)
		frappe.setup_module_map.assert_called_once_with(include_all_apps=True)
		self.assertEqual(frappe.local.request_cache, {})
		self.assertIsNone(frappe.local.app_modules)
		self.assertIsNone(frappe.local.module_app)
		self.assertEqual(registry_content, "frappe\napex\n")

	def test_canonical_state_does_not_write_or_clear_caches(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			apps_path = Path(temp_dir) / "apps.txt"
			apps_path.write_text("frappe\napex\n", encoding="utf-8")
			request_cache = {"sentinel": object()}
			frappe = self._frappe(
				json.dumps(["frappe", "apex", "erpnext", "hrms"]),
				temp_dir,
				request_cache=request_cache,
			)

			with patch.object(bootstrap, "frappe", frappe):
				bootstrap.before_migrate()

		frappe.db.set_global.assert_not_called()
		frappe.cache.delete_value.assert_not_called()
		frappe.setup_module_map.assert_not_called()
		self.assertIs(frappe.local.request_cache, request_cache)
		self.assertIn("sentinel", request_cache)

	def test_changed_state_tolerates_missing_request_cache(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			apps_path = Path(temp_dir) / "apps.txt"
			apps_path.write_text("apex_habitat\n", encoding="utf-8")
			frappe = self._frappe(json.dumps(["apex_habitat"]), temp_dir)
			del frappe.local.request_cache

			with patch.object(bootstrap, "frappe", frappe):
				bootstrap.before_migrate()

		frappe.db.set_global.assert_called_once_with("installed_apps", json.dumps(["apex"]))

	def test_repairs_either_mixed_registry_state(self):
		states = (
			(["frappe", "apex_habitat"], "frappe\napex\n"),
			(["frappe", "apex"], "frappe\napex_habitat\n"),
		)
		for installed_apps, registry in states:
			with self.subTest(installed_apps=installed_apps, registry=registry):
				with tempfile.TemporaryDirectory() as temp_dir:
					apps_path = Path(temp_dir) / "apps.txt"
					apps_path.write_text(registry, encoding="utf-8")
					frappe = self._frappe(json.dumps(installed_apps), temp_dir)

					with patch.object(bootstrap, "frappe", frappe):
						bootstrap.before_migrate()

					self.assertEqual(
						apps_path.read_text(encoding="utf-8"), "frappe\napex\n"
					)
					frappe.setup_module_map.assert_called_once_with(include_all_apps=True)

	def test_canonicalizes_successful_patch_log_rows_before_rebuilding_modules(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			apps_path = Path(temp_dir) / "apps.txt"
			apps_path.write_text("frappe\napex\n", encoding="utf-8")
			frappe = self._frappe(
				json.dumps(["frappe", "apex"]),
				temp_dir,
				legacy_patches=True,
			)

			with patch.object(bootstrap, "frappe", frappe):
				bootstrap.before_migrate()

		queries = [call.args for call in frappe.db.sql.call_args_list]
		self.assertEqual(len(queries), 2)
		self.assertIn("SELECT", queries[0][0])
		self.assertIn("UPDATE", queries[1][0])
		self.assertIn("`skipped` = 0", queries[1][0])
		self.assertEqual(queries[1][1][0], bootstrap.NEW_DOTTED)
		self.assertEqual(queries[1][1][2], bootstrap.OLD_DOTTED)
		frappe.setup_module_map.assert_called_once_with(include_all_apps=True)


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

	def test_canonical_hooks_also_register_the_temporary_mixed_state_bridge(self):
		self.assertEqual(
			canonical_hooks.before_migrate,
			["apex.hooks.bootstrap_legacy_app_identity"],
		)

	def test_canonical_bridge_delegates_to_the_compatibility_bootstrap(self):
		with patch.object(bootstrap, "before_migrate") as compatibility_bootstrap:
			canonical_hooks.bootstrap_legacy_app_identity()

		compatibility_bootstrap.assert_called_once_with()

	def test_legacy_modules_file_matches_the_canonical_module_map(self):
		repo_root = Path(__file__).resolve().parents[2]

		self.assertEqual(
			(repo_root / "apex_habitat" / "modules.txt").read_text(encoding="utf-8"),
			(repo_root / "apex" / "modules.txt").read_text(encoding="utf-8"),
		)


class TestCompatibilityPackaging(unittest.TestCase):
	REPO_ROOT = Path(__file__).resolve().parents[2]

	def test_setuptools_discovers_canonical_and_legacy_packages(self):
		packages = set(find_packages(where=os.fspath(self.REPO_ROOT)))

		self.assertIn("apex", packages)
		self.assertIn("apex_habitat", packages)

	def test_active_build_backend_explicitly_includes_both_packages(self):
		config = (self.REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

		self.assertIn('requires = ["setuptools>=68", "wheel"]', config)
		self.assertIn('build-backend = "setuptools.build_meta"', config)
		self.assertIn("[tool.setuptools.packages.find]", config)
		self.assertIn('include = ["apex*", "apex_habitat*"]', config)

	def test_source_manifest_includes_the_legacy_package(self):
		manifest = (self.REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")

		self.assertIn("recursive-include apex_habitat *.py *.txt", manifest)

	def test_built_wheel_contains_frappe_runtime_assets(self):
		runtime_suffixes = {
			".py",
			".json",
			".js",
			".css",
			".html",
			".md",
			".txt",
			".csv",
			".woff2",
			".png",
			".svg",
			".webmanifest",
		}
		required = set()
		for package in ("apex", "apex_habitat"):
			for path in (self.REPO_ROOT / package).rglob("*"):
				if not path.is_file() or path.suffix not in runtime_suffixes:
					continue
				if {"__pycache__", "node_modules"}.intersection(path.parts):
					continue
				required.add(path.relative_to(self.REPO_ROOT).as_posix())

		with tempfile.TemporaryDirectory() as temp_dir:
			temp_root = Path(temp_dir)
			source_root = temp_root / "source"
			source_root.mkdir()
			for filename in (
				"pyproject.toml",
				"setup.py",
				"MANIFEST.in",
				"README.md",
				"license.txt",
			):
				shutil.copy2(self.REPO_ROOT / filename, source_root / filename)
			for package in ("apex", "apex_habitat"):
				shutil.copytree(
					self.REPO_ROOT / package,
					source_root / package,
					ignore=shutil.ignore_patterns(
						"__pycache__", "*.pyc", "node_modules", ".gitkeep"
					),
				)

			wheel_dir = temp_root / "wheel"
			wheel_dir.mkdir()
			result = subprocess.run(
				[
					sys.executable,
					"-m",
					"pip",
					"wheel",
					"--no-deps",
					"--no-build-isolation",
					"--wheel-dir",
					os.fspath(wheel_dir),
					os.fspath(source_root),
				],
				capture_output=True,
				text=True,
			)
			self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
			wheel_path = next(wheel_dir.glob("apex-*.whl"))
			with zipfile.ZipFile(wheel_path) as archive:
				wheel_files = set(archive.namelist())

		self.assertEqual(required - wheel_files, set())


class TestLegacyMigrationWorkflow(unittest.TestCase):
	WORKFLOW = (
		Path(__file__).resolve().parents[2]
		/ ".github"
		/ "workflows"
		/ "migrate-check.yml"
	)

	def test_triggers_cover_the_bridge_and_packaging_inputs(self):
		workflow = self.WORKFLOW.read_text(encoding="utf-8")

		for required in (
			"workflow_dispatch:",
			'".github/workflows/migrate-check.yml"',
			'"apex/tests/test_app_identity_bootstrap.py"',
			'"apex_habitat/**"',
			'"pyproject.toml"',
			'"setup.py"',
			'"MANIFEST.in"',
		):
			with self.subTest(required=required):
				self.assertIn(required, workflow)

	def test_stages_and_proves_the_exact_legacy_identity(self):
		workflow = self.WORKFLOW.read_text(encoding="utf-8")

		for required in (
			"install-app apex_habitat",
			'assert apps.count("apex_habitat") == 1 and "apex" not in apps',
			'test "$installed_application" = "apex_habitat"',
			'test "$module_identity" = "apex_habitat"',
			'test "$registry_identity" = "apex_habitat"',
			'test "$schema_lag" = "0"',
			"apex_habitat.patches.v1_x.add_asl_composite_index",
		):
			with self.subTest(required=required):
				self.assertIn(required, workflow)

	def test_runs_the_standard_update_equivalent_order(self):
		workflow = self.WORKFLOW.read_text(encoding="utf-8")
		command = "bench --site test.localhost migrate"
		first_migrate = workflow.find(command)
		build = workflow.find("bench build --app apex", first_migrate + len(command))

		self.assertGreaterEqual(first_migrate, 0)
		self.assertGreater(build, first_migrate)
		self.assertEqual(workflow.count(command), 1)

	def test_rehearses_a_real_legacy_schema_before_the_single_migrate(self):
		workflow = self.WORKFLOW.read_text(encoding="utf-8")

		for required in (
			"d4b153bf36d6a8d4a752631377f8f50bf447430e",
			"install-app apex_habitat",
			"mv apps/apex_habitat apps/apex",
			"information_schema.columns",
			"holder_type",
			'git checkout --detach "$GITHUB_SHA"',
			"git checkout --detach FETCH_HEAD",
			"bench setup requirements --python",
		):
			with self.subTest(required=required):
				self.assertIn(required, workflow)

	def test_verifies_every_canonical_cutover_surface_exactly(self):
		workflow = self.WORKFLOW.read_text(encoding="utf-8")

		for required in (
			'assert apps.count("apex") == 1 and "apex_habitat" not in apps',
			'test "$installed_application" = "apex"',
			'test "$module_identity" = "apex"',
			"apex.patches.v2_0.rename_app_apex_habitat_to_apex",
			'test "$patch_log" = "apex.patches.v2_0.rename_app_apex_habitat_to_apex"',
			'test "$historical_patch_count" = "1"',
			'test "$legacy_success_count" = "0"',
			'test "$schema_synced" = "1"',
			'test "$registry_identity" = "apex"',
		):
			with self.subTest(required=required):
				self.assertIn(required, workflow)

		self.assertNotIn("${{ secrets.", workflow)


if __name__ == "__main__":
	unittest.main()
