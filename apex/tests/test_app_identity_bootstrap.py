"""Tests for the temporary legacy app identity bootstrap."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apex_habitat import bootstrap, hooks
from apex_habitat.bootstrap import IdentityCutoverError, canonicalize_installed_apps


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
