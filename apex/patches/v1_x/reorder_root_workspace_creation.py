# Copyright (c) 2026, AFMCO and contributors
"""Make each module's ROOT workspace the deterministic breadcrumb target.

Desk breadcrumbs resolve a DocType's workspace as
``module_wise_workspaces[module][0]`` (frappe breadcrumbs.js), and that list is
built ordered by the Workspace row's ``creation`` column
(Workspace.get_module_wise_workspaces, ``order_by="creation"``). A workspace JSON
that ships no ``creation`` value gets the import moment from ``db_insert``, and
``get_doc_files`` scans the folder with bare ``os.listdir`` (frappe/model/sync.py),
which is DIRECTORY order, not alphabetical — so which workspace lands first is
arbitrary. Worse, every later JSON change re-imports via delete+insert,
re-stamping ``creation = now()`` and dropping that workspace to LAST. Net effect:
an arbitrary sub-workspace wins the module breadcrumb.

SUPERSEDED for the modules that ship a pinned ``creation``. A past
``creation`` in the workspace JSON survives both install paths untouched
(document.py set_user_and_timestamp skips the overwrite under in_install /
in_patch / in_migrate), so the ordering is restored by the very re-import that
used to break it and this pass finds nothing to do. What remains here is the
compensator for rows already in a database whose JSON carries no pin — note it
ABSTAINS on any module without exactly one public root, which is why it never
reached Habitat once Backend Engines was relocated into that module.

Fix: rewrite ONLY the DB ``creation`` of each module's single public root
workspace (``parent_page == ""``) to one second before its earliest sibling, so
the root always sorts first. ``modified`` is deliberately untouched — bumping it
would trip the sync timestamp-skip check (import_file.py) and freeze future
workspace JSON syncs.

One callable, registered three ways (idempotent, order-safe):
- patches.txt ``[post_model_sync]`` — one-time tracked fix on deployed sites;
- ``after_migrate`` — self-heals after any future re-import re-stamps creation;
- ``after_install`` — fresh sites mark patches complete WITHOUT running them.

Skips a module without exactly one public root (Apex Core ships two peer roots
by design) and a module with no sibling workspaces. PRUNE from patches.txt only
if the after_migrate/after_install hooks stay registered.

PERMANENT compensator (ratified — Option A): the root cause is frappe's unordered
workspace-sync directory import (``creation`` is stamped at import time and never
ordered upstream). This is an accepted, standing trade-off, not temporary debt.
"""

import frappe
from frappe.utils import add_to_date, get_datetime

APP_NAME = "apex"


def execute():
    changed = False
    for module in frappe.get_module_list(APP_NAME):
        rows = frappe.get_all(
            "Workspace",
            filters={"module": module, "public": 1, "for_user": ""},
            fields=["name", "parent_page", "creation"],
        )
        roots = [r for r in rows if not r.parent_page]
        if len(roots) != 1:
            # [#t42qlr]
            continue
        root = roots[0]
        siblings = [get_datetime(r.creation) for r in rows if r.name != root.name and r.creation]
        if not siblings:
            continue
        earliest_sibling = min(siblings)
        if root.creation and get_datetime(root.creation) < earliest_sibling:
            continue  # [#pmemh5]
        frappe.db.set_value(
            "Workspace",
            root.name,
            "creation",
            add_to_date(earliest_sibling, seconds=-1),
            update_modified=False,
        )
        changed = True
    if changed:
        # [#6t867j]
        frappe.clear_cache()
