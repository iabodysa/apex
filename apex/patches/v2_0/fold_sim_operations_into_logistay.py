# Copyright (c) 2026, AFMCO and contributors
"""Fold the retired ``SIM Operations`` module into ``Logistay``.

The SIM telecom source moved from ``apex/sim_operations/`` to ``apex/logistay/``, the
module line is gone from modules.txt, and the standalone SIM Operations workspace was
folded into Habitat's Custody hub (the Masar workspace was likewise folded into the
Salis root). Migrate is import-only: it re-imports the moved is_standard JSON under its
new module, but it never reconciles a module that stopped existing nor a workspace whose
JSON was deleted. This patch repairs what a deployed site still carries:

  * every standard record still stamped ``module = "SIM Operations"`` -> ``Logistay``
    (DocType, Report, Page, Number Card, Notification, Workspace, Dashboard Chart,
    Custom Field, ... — discovered from the schema, never hand-listed);
  * every stored dotted path ``apex.sim_operations.*`` -> ``apex.logistay.*``
    (Scheduled Job Type / Number Card / Dashboard Chart ``method``, Server Script
    ``script``, Notification condition text, and any other config column that persists
    a Python path) via the same token-gated DB sweep the app-identity cutover used;
  * the orphaned ``SIM Operations`` and ``Masar`` Workspace rows plus any User still
    pinned to one via ``default_workspace``;
  * the now-dead ``SIM Operations`` Module Def.

NOTHING IS DROPPED OR RECREATED — every SIM Card / Telecom Contract / SIM Custody
Assignment / Telecom Billing Document row and table is left untouched; only the module
label and the dotted code paths that point at it are rewritten.

post_model_sync: the moved DocTypes must already be synced under Logistay, and the
Scheduled Job Type repoint must land before ``sync_jobs()`` (which runs after all
post-model patches) so the daily SIM watch keeps its existing row instead of gaining a
duplicate. Fully guarded and idempotent — the module filter matches nothing and the
LOCATE-gated sweep rewrites nothing on a second migrate, and a fresh install (which
never had the module) is a complete no-op.

Correction: that last clause was FALSE until the ghost Module Def was dropped. The modules.txt line above was
never actually dropped, so ``add_module_defs`` kept minting a ``SIM Operations`` Module
Def on every fresh install while ``set_all_patches_as_completed`` logged this patch as
done without running it. ``drop_ghost_sim_operations_module_def`` is the one-time repair
for the sites that gap produced; modules.txt is now correct, so the clause holds.
"""

from __future__ import annotations

import re

import frappe

OLD_MODULE = "SIM Operations"
NEW_MODULE = "Logistay"
OLD_DOTTED = "apex.sim_operations."
NEW_DOTTED = "apex.logistay."

_FOLDED_WORKSPACES = ("SIM Operations", "Masar")

_SAFE_IDENT = re.compile(r"[\w ]+")

_SWEEP_SKIP_TABLES = {
    "tabPatch Log",
    "tabVersion",
    "tabError Log",
    "tabError Snapshot",
    "tabScheduled Job Log",
    "tabActivity Log",
    "tabAccess Log",
    "tabView Log",
    "tabRoute History",
    "tabDeleted Document",
    "tabEmail Queue",
}

_TEXT_TYPES = ("char", "varchar", "text", "tinytext", "mediumtext", "longtext")


def execute() -> None:
    _ensure_target_module()
    _repoint_module_stamps()
    _rewrite_dotted_paths()
    _drop_folded_workspaces()
    _drop_retired_module_def()
    frappe.db.commit()


def _ensure_target_module() -> None:
    """Logistay ships in modules.txt, so its Module Def normally already exists; create
    it only if a site somehow lacks it, so the repoint below never points at nothing."""
    if frappe.db.exists("Module Def", NEW_MODULE):
        return
    frappe.get_doc(
        {"doctype": "Module Def", "module_name": NEW_MODULE, "app_name": "apex"}
    ).insert(ignore_permissions=True)  # audit-ok: install-time metadata, no user data


def _module_carriers() -> list[str]:
    """Every DocType with a ``module`` Link to Module Def — discovered from the schema so
    a Frappe version that adds another module-stamped record type is covered for free."""
    carriers = frappe.get_all(
        "DocField",
        filters={
            "parenttype": "DocType",
            "fieldname": "module",
            "fieldtype": "Link",
            "options": "Module Def",
        },
        pluck="parent",
    )
    return sorted(set(carriers) | {"DocType"})


def _repoint_module_stamps() -> None:
    """Restamp every record still claiming the retired module. Never deletes a row."""
    for doctype in _module_carriers():
        if not frappe.db.table_exists(doctype) or not frappe.db.has_column(doctype, "module"):
            continue
        if not frappe.db.exists(doctype, {"module": OLD_MODULE}):
            continue
        frappe.db.set_value(
            doctype, {"module": OLD_MODULE}, "module", NEW_MODULE, update_modified=False
        )
        frappe.clear_cache(doctype=doctype)


def _rewrite_dotted_paths() -> None:
    """DB-wide sweep: rewrite the dead dotted prefix in place in every text column.

    Gated by LOCATE (literal substring — no LIKE wildcard/underscore trap), so a re-run
    matches nothing and rewrites nothing.
    """
    if frappe.db.db_type != "mariadb":
        _rewrite_known_method_columns()
        return

    type_placeholders = ", ".join(["%s"] * len(_TEXT_TYPES))
    columns = frappe.db.sql(
        f"""
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND data_type IN ({type_placeholders})
          AND table_name LIKE 'tab%%'
        """,
        (frappe.conf.db_name, *_TEXT_TYPES),
        as_dict=True,
    )

    for col in columns:
        table, column = col.table_name, col.column_name
        if table in _SWEEP_SKIP_TABLES:
            continue
        if not (_SAFE_IDENT.fullmatch(table) and _SAFE_IDENT.fullmatch(column)):
            continue
        frappe.db.sql(
            f"UPDATE `{table}` "
            f"SET `{column}` = REPLACE(`{column}`, %s, %s) "
            f"WHERE LOCATE(%s, `{column}`) > 0",
            (OLD_DOTTED, NEW_DOTTED, OLD_DOTTED),
        )


def _rewrite_known_method_columns() -> None:
    """Non-MariaDB fallback: heal the config carriers this app actually ships rows for."""
    for doctype, field in (
        ("Scheduled Job Type", "method"),
        ("Number Card", "method"),
        ("Dashboard Chart", "method"),
    ):
        if not frappe.db.table_exists(doctype):
            continue
        for row in frappe.get_all(doctype, fields=["name", field]):
            value = row.get(field) or ""
            if OLD_DOTTED not in value:
                continue
            frappe.db.set_value(
                doctype,
                row.name,
                field,
                value.replace(OLD_DOTTED, NEW_DOTTED),
                update_modified=False,
            )


def _drop_folded_workspaces() -> None:
    """Delete the Workspace rows whose is_standard JSON is gone (content folded into
    Custody / the Salis root). Their DocType/report/page targets are untouched."""
    if frappe.db.has_column("User", "default_workspace"):
        for name in _FOLDED_WORKSPACES:
            if frappe.db.exists("User", {"default_workspace": name}):
                frappe.db.set_value(
                    "User",
                    {"default_workspace": name},
                    "default_workspace",
                    "",
                    update_modified=False,
                )

    dropped = False
    for name in _FOLDED_WORKSPACES:
        if frappe.db.exists("Workspace", name):
            frappe.delete_doc("Workspace", name, ignore_permissions=True, force=True)  # audit-ok
            dropped = True
    if dropped:
        frappe.clear_cache()


def _drop_retired_module_def() -> None:
    """Remove the dead Module Def last — every row that referenced it is repointed above."""
    if frappe.db.exists("Module Def", OLD_MODULE):
        frappe.db.delete("Module Def", {"name": OLD_MODULE})
