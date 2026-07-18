"""Canonicalize the installed app identity before normal migration patches."""

import json
import os
import stat
import tempfile
from pathlib import Path

import frappe

OLD = "apex_habitat"
NEW = "apex"


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


def before_migrate():
	"""Rewrite the legacy installed app identity before migration begins."""
	serialized_apps = frappe.db.get_global("installed_apps")
	canonical_apps = canonicalize_installed_apps(serialized_apps)
	installed_apps = json.loads(serialized_apps)

	if installed_apps == canonical_apps:
		return

	frappe.db.set_global("installed_apps", json.dumps(canonical_apps))
	frappe.cache.delete_value(["app_hooks", "all_apps"])
	request_cache = getattr(frappe.local, "request_cache", None)
	if request_cache is not None:
		request_cache.clear()
