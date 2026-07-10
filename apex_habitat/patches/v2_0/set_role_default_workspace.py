# Copyright (c) 2026, AFMCO and contributors
"""V2.0.0 — B5 (P-159): stamp the daily role workspace as each user's default landing.

Frappe has NO per-role default-workspace primitive; the only per-user lever is
User.default_workspace. This run-once patch maps each of the four task-first daily
workspaces to its role and stamps default_workspace on every user holding that role.

GUARD: only stamps when the user's default_workspace is EMPTY (never clobbers a choice
the user set for themselves); skips a role whose workspace row is not yet present.
Idempotent: a re-run finds every relevant user already stamped (or self-chosen) and
does nothing. Ordering: sidebar sequence_id (1.0-1.3) already sorts these pages first;
this patch makes the daily page the actual OPEN target. PRUNE once every deployed site
has run it (tracked in tabPatch Log).
"""

import frappe

ROLE_WORKSPACE = {
	"Resident Supervisor": "Resident Supervisor",
	"Fleet Supervisor": "Fleet Supervisor",
	"Safety Officer": "Safety Officer",
	"Maintenance Technician": "Maintenance Technician",
}


def execute():
	for role, workspace in ROLE_WORKSPACE.items():
		if not frappe.db.exists("Workspace", workspace):
			continue
		users = frappe.get_all(
			"Has Role",
			filters={"role": role, "parenttype": "User"},
			pluck="parent",
		)
		for user in set(users):
			if user in ("Administrator", "Guest"):
				continue
			if frappe.db.get_value("User", user, "default_workspace"):
				continue
			frappe.db.set_value(
				"User", user, "default_workspace", workspace, update_modified=False
			)
