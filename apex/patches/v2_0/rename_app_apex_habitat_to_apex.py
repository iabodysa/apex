# Copyright (c) 2026, AFMCO and contributors
"""TEMPORARY app-identity cutover: apex_habitat -> apex.

DELETE THIS FILE (and its patches.txt line) only after the sole production
site records it in tabPatch Log. The app CODE is already renamed to `apex`;
this rewrites the filesystem and DB references a pre-rename 1.60.x site still
carries so a single `bench migrate` completes the rename:

  * the exact `apex_habitat` line in sites/apps.txt -> `apex`, atomically;
  * every stored dotted path `apex_habitat.<module>...` -> `apex.<module>...`
    (Number Card / Dashboard Chart .method, Scheduled Job Type .method,
    Server Script .script, Notification/Assignment Rule condition text, and
    any other config column that persists a Python path) via a DB-wide,
    token-gated sweep;
  * Module Def.app_name          'apex_habitat' -> 'apex';
  * Installed Application child rows .app_name  'apex_habitat' -> 'apex';
  * the installed_apps global list element      'apex_habitat' -> 'apex'.

AUTOMATIC CUTOVER SEQUENCE:
The temporary legacy before_migrate hook canonicalizes the installed_apps
global while `apex_habitat` remains importable, allowing Frappe to discover
the canonical `apex` patches. This patch then repairs sites/apps.txt with an
atomic replacement, invalidates app-discovery caches, and performs the DB
sweep below. No manual registry edit is required.

Idempotent: the dotted sweep only touches rows still containing the literal
`apex_habitat.`; the exact-value renames only touch rows still equal to
`apex_habitat`. A second migrate is a no-op.
"""

import json
import re
from pathlib import Path

import frappe

from apex_habitat.bootstrap import rewrite_bench_apps_registry

# Identifier allowlist for the DB-wide sweep: Frappe table/column names are
# word chars + spaces only (e.g. `tabNumber Card`, `email_id`). Every table /
# column comes from information_schema (never request input), but the back-
# quoted identifiers are still validated with `.fullmatch` before they reach
# the SQL text so a non-identifier value can never break out of the quoting.
_SAFE_IDENT = re.compile(r"[\w ]+")

OLD = "apex_habitat"
NEW = "apex"
# Distinctive dotted prefix — only ever a dead app path. Never matches the
# healthy new form `apex.` nor the bare token inside patch/log names.
OLD_DOTTED = "apex_habitat."
NEW_DOTTED = "apex."

# Append-only / audit / bookkeeping tables: skip the sweep. Rewriting their
# historical blobs is pointless churn (and Patch Log rows literally contain the
# bare token as part of patch names). Config tables are all still swept.
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


def execute():
    _rename_bench_apps_registry()
    _rewrite_dotted_paths()
    _rename_module_def()
    _rename_installed_application_rows()
    _rename_installed_apps_global()


def _rename_bench_apps_registry():
    apps_path = Path(frappe.local.sites_path) / "apps.txt"
    if not rewrite_bench_apps_registry(apps_path):
        return

    frappe.cache.delete_value(["app_hooks", "all_apps"])
    request_cache = getattr(frappe.local, "request_cache", None)
    if request_cache is not None:
        request_cache.clear()


def _rewrite_dotted_paths():
    """DB-wide sweep: every text column, rewrite the dead dotted prefix in place.

    Gated by LOCATE (literal substring, no LIKE wildcard/underscore trap) so a
    re-run matches nothing and rewrites nothing -> idempotent.
    """
    if frappe.db.db_type != "mariadb":
        # Prod is MariaDB; on other engines fall back to the two known method
        # carriers so the critical dashboards/jobs still heal.
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
        table = col.table_name
        if table in _SWEEP_SKIP_TABLES:
            continue
        column = col.column_name
        # Guard the interpolated identifiers (defence-in-depth over the trusted
        # information_schema source): skip anything that is not a plain
        # word-chars/space identifier before it is spliced into the DDL.
        if not (_SAFE_IDENT.fullmatch(table) and _SAFE_IDENT.fullmatch(column)):
            continue
        frappe.db.sql(
            # identifiers come from information_schema and are `.fullmatch`-guarded above.
            f"UPDATE `{table}` "
            f"SET `{column}` = REPLACE(`{column}`, %s, %s) "
            f"WHERE LOCATE(%s, `{column}`) > 0",
            (OLD_DOTTED, NEW_DOTTED, OLD_DOTTED),
        )


def _rewrite_known_method_columns():
    """Non-MariaDB fallback: heal the two config carriers we ship rows for."""
    for doctype, field in (("Number Card", "method"), ("Scheduled Job Type", "method")):
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


def _rename_module_def():
    if frappe.db.exists("Module Def", {"app_name": OLD}):
        frappe.db.set_value(
            "Module Def", {"app_name": OLD}, "app_name", NEW, update_modified=False
        )


def _rename_installed_application_rows():
    # Child rows of the Single "Installed Applications" (tabInstalled Application).
    if frappe.db.exists("Installed Application", {"app_name": OLD}):
        frappe.db.set_value(
            "Installed Application",
            {"app_name": OLD},
            "app_name",
            NEW,
            update_modified=False,
        )


def _rename_installed_apps_global():
    # Authoritative list migrate reads (tabDefaultValue defkey=installed_apps).
    # Normally already flipped pre-migrate (see BOOTSTRAP CAVEAT); this only
    # heals a mixed state. Dedupe so `apex` never appears twice.
    apps = json.loads(frappe.db.get_global("installed_apps") or "[]")
    if OLD not in apps:
        return
    out, seen = [], set()
    for app in apps:
        app = NEW if app == OLD else app
        if app not in seen:
            seen.add(app)
            out.append(app)
    frappe.db.set_global("installed_apps", json.dumps(out))
