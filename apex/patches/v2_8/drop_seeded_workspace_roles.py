# Copyright (c) 2026, afmcoltd
"""Give a Workspace back the visibility its own file declares.

A retired seeder derived each roleless public Workspace's audience from the DocPerms of
the doctypes it links to, keeping only rows with ``if_owner: 0``. A PERSONAL workspace is
built on the opposite permission: a person sees their OWN rows. So the derivation was
structurally blind to the very rule that makes such a workspace personal, read "nobody
may see this", and wrote a System Manager restriction into the database.

Measured on a live site: My Tasks — the personal queue holding ToDo, Workflow Action and
Notification Log — carried one role row, System Manager, while its own JSON declares
none. Every ordinary operator lost their task list, and the file that would have
explained it was empty.

Workspace is in ``IMPORTABLE_DOCTYPES`` (frappe/model/sync.py:17-37), so the file is the
source of truth and ``sync_all`` reapplies it on every migrate. What it cannot do is
remove a child row the file never contained: ``import_file`` writes the file's rows and
leaves an extra one standing. This patch removes those, once.

Only workspaces whose SHIPPED FILE declares no roles are touched. A workspace that
declares its own audience keeps it, because the seeder skipped those and never wrote to
them.

CONTRACT: an empty ``roles`` array means "every desk user may see it". If a workspace
here should in fact be restricted, the restriction belongs in its JSON, not in a row
this patch would delete again on the next site.
"""

import json
import pathlib

import frappe


def execute():
    """Delete role rows on public Workspaces whose own file declares none."""
    app_root = pathlib.Path(frappe.get_app_path("apex"))

    roleless = set()
    for path in app_root.rglob("workspace/*/*.json"):
        try:
            data = json.loads(path.read_text())
        except (ValueError, OSError):
            continue
        if data.get("doctype") != "Workspace" or not data.get("public"):
            continue
        if not (data.get("roles") or []):
            roleless.add(data.get("name"))

    if not roleless:
        return

    for name in sorted(roleless):
        if not frappe.db.exists("Workspace", name):
            continue
        if not frappe.db.exists("Has Role", {"parenttype": "Workspace", "parent": name}):
            continue
        frappe.db.delete("Has Role", {"parenttype": "Workspace", "parent": name})
        print(f"apex: cleared seeded roles on Workspace {name}")

    frappe.clear_cache()
