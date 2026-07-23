# Copyright (c) 2026, AFMCO and contributors
"""A-042 — retire the four per-role landing Workspaces (ONE-TIME).

The Resident Supervisor / Fleet Supervisor / Safety Officer / Maintenance
Technician landing pages were folded into the business-domain workspaces
(Housing / Safety / fleet + the Salis tree). Their is_standard JSON is deleted,
but migrate is import-only and never reconciles a removed JSON, so the DB rows
linger and shadow the domain navigation ([[reference-frappe-orphan-row-on-json-delete]]).

This deletes those rows and reverses the now-retired set_role_default_workspace
stamp: any user whose default_workspace still points at a removed page is cleared
so they fall back to their domain default. Idempotent, no-op on fresh installs /
re-run. PRUNE once every deployed site has run it (tracked in tabPatch Log).
"""

import frappe

REMOVED_WORKSPACES = [
	"Resident Supervisor",
	"Fleet Supervisor",
	"Safety Officer",
	"Maintenance Technician",
]


def execute():
	for name in REMOVED_WORKSPACES:
		# Reverse the retired default-landing stamp before dropping the row so no
		# User is left pointing at a workspace that no longer exists.
		for user in frappe.get_all(
			"User", filters={"default_workspace": name}, pluck="name"
		):
			frappe.db.set_value(
				"User", user, "default_workspace", None, update_modified=False
			)
		if frappe.db.exists("Workspace", name):
			frappe.delete_doc(
				"Workspace", name, ignore_permissions=True, force=True  # audit-ok — migration deletes orphaned is_standard Workspace rows
			)
