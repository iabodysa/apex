"""Canonicalize the installed app identity before normal migration patches."""

import json
import os
import stat
import tempfile
from pathlib import Path

import frappe

OLD = "apex_habitat"
NEW = "apex"
OLD_DOTTED = f"{OLD}."
NEW_DOTTED = f"{NEW}."

APP_DISCOVERY_CACHE_KEYS = [
	"app_hooks",
	"installed_apps",
	"all_apps",
	"app_modules",
	"installed_app_modules",
	"module_app",
	"module_installed_app",
]


class IdentityCutoverError(RuntimeError):
	"""Raised when the installed app registry cannot be cut over safely."""


def _atomic_write(path, content):
	"""Replace a UTF-8 text file atomically while retaining its access mode."""
	path = Path(path)
	mode = stat.S_IMODE(path.stat().st_mode)
	file_descriptor, temp_name = tempfile.mkstemp(
		dir=path.parent,
		prefix=f".{path.name}.",
		suffix=".tmp",
	)
	temp_path = Path(temp_name)

	try:
		temp_file = os.fdopen(
			file_descriptor,
			"w",
			encoding="utf-8",
			newline="",
		)
		file_descriptor = None
		with temp_file:
			temp_file.write(content)
			temp_file.flush()
			os.fsync(temp_file.fileno())
		os.chmod(temp_path, mode)
		os.replace(temp_path, path)
	finally:
		if file_descriptor is not None:
			os.close(file_descriptor)
		try:
			temp_path.unlink()
		except FileNotFoundError:
			pass


def rewrite_bench_apps_registry(path):
	"""Atomically replace the sole legacy apps.txt identity with the canonical one."""
	path = Path(path)
	with path.open("r", encoding="utf-8", newline="") as apps_file:
		content = apps_file.read()

	lines = content.splitlines(keepends=True)
	logical_lines = [line.rstrip("\r\n") for line in lines]
	old_count = logical_lines.count(OLD)
	new_count = logical_lines.count(NEW)

	if old_count == 0 and new_count == 1:
		return False
	if old_count != 1 or new_count != 0:
		raise IdentityCutoverError(
			"sites/apps.txt has an ambiguous Apex application identity"
		)

	rewritten_lines = []
	for line, logical_line in zip(lines, logical_lines, strict=True):
		if logical_line == OLD:
			line_ending = line[len(logical_line) :]
			rewritten_lines.append(f"{NEW}{line_ending}")
		else:
			rewritten_lines.append(line)

	_atomic_write(path, "".join(rewritten_lines))
	return True


def canonicalize_installed_apps(serialized_apps):
	"""Return installed apps with the legacy identity replaced by the canonical one."""
	try:
		installed_apps = json.loads(serialized_apps)
	except (json.JSONDecodeError, TypeError) as exc:
		raise IdentityCutoverError("installed_apps must contain valid JSON") from exc

	if not isinstance(installed_apps, list) or not all(
		isinstance(app, str) for app in installed_apps
	):
		raise IdentityCutoverError("installed_apps must be a JSON list of app-name strings")

	if OLD not in installed_apps and NEW not in installed_apps:
		raise IdentityCutoverError(
			"installed_apps contains neither the legacy nor canonical app identity"
		)

	canonical_apps = []
	identity_added = False
	for app in installed_apps:
		if app not in (OLD, NEW):
			canonical_apps.append(app)
			continue
		if not identity_added:
			canonical_apps.append(NEW)
			identity_added = True

	return canonical_apps


def canonicalize_successful_patch_log_identities():
	"""Map successful legacy patch evidence before Frappe snapshots it."""
	legacy_rows = frappe.db.sql(
		"""
		SELECT `name`
		FROM `tabPatch Log`
		WHERE `skipped` = 0
		  AND LOCATE(%s, `patch`) = 1
		LIMIT 1
		""",
		(OLD_DOTTED,),
	)
	if not legacy_rows:
		return False

	frappe.db.sql(
		"""
		UPDATE `tabPatch Log`
		SET `patch` = CONCAT(%s, SUBSTRING(`patch`, %s))
		WHERE `skipped` = 0
		  AND LOCATE(%s, `patch`) = 1
		""",
		(NEW_DOTTED, len(OLD_DOTTED) + 1, OLD_DOTTED),
	)
	return True


def _rebuild_app_discovery():
	"""Discard legacy app caches and rebuild the canonical module map."""
	frappe.cache.delete_value(APP_DISCOVERY_CACHE_KEYS)
	request_cache = getattr(frappe.local, "request_cache", None)
	if request_cache is not None:
		request_cache.clear()

	frappe.local.app_modules = None
	frappe.local.module_app = None
	frappe.setup_module_map(include_all_apps=True)


def before_migrate():
	"""Canonicalize every app-discovery input before patches and schema sync."""
	serialized_apps = frappe.db.get_global("installed_apps")
	canonical_apps = canonicalize_installed_apps(serialized_apps)
	installed_apps = json.loads(serialized_apps)
	registry_changed = rewrite_bench_apps_registry(
		Path(frappe.local.sites_path) / "apps.txt"
	)
	patch_log_changed = canonicalize_successful_patch_log_identities()
	installed_apps_changed = installed_apps != canonical_apps

	if installed_apps_changed:
		frappe.db.set_global("installed_apps", json.dumps(canonical_apps))

	if registry_changed or patch_log_changed or installed_apps_changed:
		_rebuild_app_discovery()
