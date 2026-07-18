"""Canonicalize the installed app identity before normal migration patches."""

import json

import frappe

OLD = "apex_habitat"
NEW = "apex"


class IdentityCutoverError(RuntimeError):
	"""Raised when the installed app registry cannot be cut over safely."""


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
