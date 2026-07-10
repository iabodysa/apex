# Copyright (c) 2026, AFMCO and contributors
"""Make each module's ROOT workspace the deterministic breadcrumb target (P-108).

Desk breadcrumbs resolve a DocType's workspace as
``module_wise_workspaces[module][0]`` (frappe breadcrumbs.js), and that list is
built ordered by the Workspace row's ``creation`` column
(Workspace.get_module_wise_workspaces, ``order_by="creation"``). Our workspace
JSONs ship no ``creation`` value, so ``db_insert`` stamps the import moment —
a fresh install imports the directory scan alphabetically, so a CHILD lands
before its module root (``costs_and_leasing`` < ``habitat``,
``compliance_and_rentals`` < ``salis``), and every later JSON change re-imports
via delete+insert, re-stamping ``creation = now()``. Net effect: an arbitrary
sub-workspace wins the module breadcrumb (follow-up to P-055).

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

APP_NAME = "apex_habitat"


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
            # no root synced yet, or peer roots (Apex Core): nothing deterministic to enforce
            continue
        root = roots[0]
        siblings = [get_datetime(r.creation) for r in rows if r.name != root.name and r.creation]
        if not siblings:
            continue
        earliest_sibling = min(siblings)
        if root.creation and get_datetime(root.creation) < earliest_sibling:
            continue  # root already sorts first — the breadcrumb target is correct
        frappe.db.set_value(
            "Workspace",
            root.name,
            "creation",
            add_to_date(earliest_sibling, seconds=-1),
            update_modified=False,
        )
        changed = True
    if changed:
        # bootinfo caches module_wise_workspaces per user; flush so open sessions reorder
        frappe.clear_cache()
