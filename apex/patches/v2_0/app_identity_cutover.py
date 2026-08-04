# Copyright (c) 2026, AFMCO and contributors
"""Operator-invoked app-identity cutover: apex_habitat -> apex.

A site installed before the package rename stores the old identity in four
places: the bench registry ``sites/apps.txt``, the ``installed_apps`` DB global,
the ``Module Def.app_name`` / ``Installed Application.app_name`` values, and any
stored dotted Python path (Number Card ``method``, Scheduled Job Type
``method``, Server Script bodies, Notification conditions).

Once the app source is upgraded past the rename, ``apex_habitat`` is no longer a
package on disk, so every one of those stored names is an unimportable module:

* ``bench migrate`` dies in ``Migrate.setUp`` -> ``clear_global_cache``
  (frappe/migrate.py:83), which loads hooks; ``_load_app_hooks`` prints
  ``Could not find app "apex_habitat"`` and re-raises (frappe/__init__.py:1592-
  1601). Rehearsed on frappe 15.109.0: it never reaches ``pre_schema_updates``.
* Hook loading drops apps absent from ``sites/apps.txt``
  (``get_installed_apps(_ensure_on_bench=True)``, frappe/__init__.py:1561-1563),
  so repairing that file is what brings the site back up - but the read is
  memoised in redis under ``all_apps`` (:1562) and ``bench clear-cache`` itself
  loads hooks, so the stale value must be dropped from redis directly.
* ``frappe.get_attr`` refuses an app missing from ``get_installed_apps()``
  (frappe/__init__.py:1744-1746), so ``bench execute apex....`` raises
  AppNotInstalledError until the DB identity is already repaired.

This is deliberately NOT a migrate patch, and must never become one: patch
discovery is gated on the same broken list. ``get_all_patches`` iterates
``frappe.get_installed_apps()`` and resolves ``frappe.get_app_path(app,
"patches.txt")`` (frappe/modules/patch_handler.py:89-102), so a pre-rename site
never opens ``apex/patches.txt`` at all.

``docs/administration/identity-upgrade.md`` is the runbook that drives these entry points.

UNREGISTERED-PATCH: a pre-rename site never reads apex/patches.txt at all, since
    frappe resolves patches per installed-app name and that name is still the
    dead package; registering this would reach only sites that are already
    canonical, sweeping every table of every healthy site to change nothing.
COVERED-BY: a deliberate operator cutover inside a maintenance window, driven by
    docs/administration/identity-upgrade.md; the pure planning helpers are exercised
    off-bench by the colocated test_app_identity_cutover.py. Reaching them needs
    an invocation that skips the ``get_attr`` gate named above.
"""

import json
import re
from pathlib import Path

OLD = "apex_habitat"
NEW = "apex"
OLD_DOTTED = f"{OLD}."
NEW_DOTTED = f"{NEW}."

REGISTRY_CANONICAL = "canonical"
REGISTRY_LEGACY = "legacy"
REGISTRY_AMBIGUOUS = "ambiguous"
REGISTRY_ABSENT = "absent"

_SAFE_IDENT = re.compile(r"[\w ]+")

SWEEP_SKIP_TABLES = frozenset(
    {
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
)

TEXT_TYPES = frozenset({"char", "varchar", "text", "tinytext", "mediumtext", "longtext"})


class IdentityCutoverError(RuntimeError):
    """Raised when the stored app identity is not in a state we can cut over."""


def classify_registry(content):
    """Name which Apex identity the raw ``sites/apps.txt`` text declares."""
    entries = [line.strip() for line in content.splitlines()]
    old_count = entries.count(OLD)
    new_count = entries.count(NEW)
    if old_count == 1 and new_count == 0:
        return REGISTRY_LEGACY
    if old_count == 0 and new_count == 1:
        return REGISTRY_CANONICAL
    if old_count == 0 and new_count == 0:
        return REGISTRY_ABSENT
    return REGISTRY_AMBIGUOUS


def rewrite_registry(content):
    """Return the ``sites/apps.txt`` text with the sole legacy identity canonical.

    Each line keeps its original ending, so a CRLF or newline-less file round
    trips unchanged. Already-canonical text is returned untouched; anything
    ambiguous raises rather than guessing which line to rewrite.
    """
    state = classify_registry(content)
    if state == REGISTRY_CANONICAL:
        return content
    if state != REGISTRY_LEGACY:
        raise IdentityCutoverError(
            f"sites/apps.txt declares an {state} Apex application identity; "
            "resolve it by hand before any cutover"
        )

    rewritten = []
    for line in content.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if body.strip() == OLD:
            rewritten.append(NEW + line[len(body) :])
        else:
            rewritten.append(line)
    return "".join(rewritten)


def canonicalize_installed_apps(serialized_apps):
    """Return the installed-app list with the legacy identity folded into the new one.

    A mixed list (both identities present) collapses to a single canonical entry
    at the first position either occupied, so the list never gains a duplicate.
    """
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
            "installed_apps names neither the legacy nor the canonical Apex identity"
        )

    canonical = []
    identity_added = False
    for app in installed_apps:
        if app not in (OLD, NEW):
            canonical.append(app)
            continue
        if not identity_added:
            canonical.append(NEW)
            identity_added = True
    return canonical


def rewrite_dotted(value):
    """Rewrite a stored dotted Python path off the dead package prefix.

    Only the trailing-dot form is matched, so the bare token and any longer
    package name that merely starts with it are both left alone.
    """
    if not value or OLD_DOTTED not in value:
        return value
    return value.replace(OLD_DOTTED, NEW_DOTTED)


def is_safe_identifier(name):
    """True when a table/column name is a plain word-chars-and-spaces identifier."""
    return bool(name) and _SAFE_IDENT.fullmatch(name) is not None


def plan_sweep(columns):
    """Choose the text columns the dotted-path sweep is allowed to rewrite.

    ``columns`` is the raw information_schema result. Non-text types, audit
    trails, non-Frappe tables and any name that is not a plain identifier are
    all dropped before a name can reach the SQL text.
    """
    planned = set()
    for column in columns:
        table = column.get("table_name") or ""
        name = column.get("column_name") or ""
        if (column.get("data_type") or "").lower() not in TEXT_TYPES:
            continue
        if not table.startswith("tab") or table in SWEEP_SKIP_TABLES:
            continue
        if not (is_safe_identifier(table) and is_safe_identifier(name)):
            continue
        planned.add((table, name))
    return sorted(planned)


def _frappe():
    """Imported lazily so every planning helper above stays testable off-bench."""
    import frappe

    return frappe


def _registry_path(frappe):
    return (Path(frappe.local.sites_path) / "apps.txt").resolve()


def _text_columns(frappe):
    """Every column of every Frappe table, unfiltered; plan_sweep does the choosing."""
    return frappe.db.sql(
        """
        SELECT table_name AS table_name, column_name AS column_name, data_type AS data_type
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name LIKE 'tab%%'
        """,
        (frappe.conf.db_name,),
        as_dict=True,
    )


def _legacy_method_rows(frappe):
    """Count the shipped config rows still pointing at the dead package path."""
    total = 0
    for doctype, field in (("Number Card", "method"), ("Scheduled Job Type", "method")):
        for row in frappe.db.get_all(doctype, fields=["name", field]):
            if OLD_DOTTED in (row.get(field) or ""):
                total += 1
    return total


def diagnose():
    """Report every place this site still stores the legacy identity. Never writes.

    Reads the bench registry FIRST and stops there while it is still legacy: any
    ORM read would load hooks for every installed app, and a stale registry
    still lists the dead one, so the query would raise before reporting
    anything. Repairing the registry file is therefore always the first step.
    """
    frappe = _frappe()
    registry_path = _registry_path(frappe)
    registry_state = REGISTRY_ABSENT
    if registry_path.exists():
        registry_state = classify_registry(registry_path.read_text(encoding="utf-8"))

    findings = {"registry_path": str(registry_path), "registry_state": registry_state}
    if registry_state != REGISTRY_CANONICAL:
        findings["next_step"] = (
            f"Rewrite {registry_path} so it names '{NEW}' before anything else; "
            "database findings are unavailable until then."
        )
        return findings

    installed_apps = json.loads(frappe.db.get_global("installed_apps") or "[]")
    findings.update(
        {
            "installed_apps": installed_apps,
            "installed_apps_legacy": OLD in installed_apps,
            "module_def_rows": frappe.db.count("Module Def", {"app_name": OLD}),
            "installed_application_rows": frappe.db.count(
                "Installed Application", {"app_name": OLD}
            ),
            "legacy_method_rows": _legacy_method_rows(frappe),
            "sweepable_columns": len(plan_sweep(_text_columns(frappe))),
        }
    )
    return findings


def preview_registry():
    """Print the corrected ``sites/apps.txt`` text for the operator to write by hand."""
    frappe = _frappe()
    path = _registry_path(frappe)
    print(rewrite_registry(path.read_text(encoding="utf-8")), end="")


def cutover():
    """Repair every stored legacy identity on this site. Idempotent; run before migrate.

    Refuses unless ``sites/apps.txt`` is already canonical. That file is bench
    wide and shared by every site on the bench, so this never writes it: one
    site's cutover must not silently re-point the registry out from under its
    neighbours. The operator edits it once, deliberately, per the runbook.
    """
    frappe = _frappe()
    registry_path = _registry_path(frappe)
    if not registry_path.exists():
        raise IdentityCutoverError(f"bench registry not found at {registry_path}")

    state = classify_registry(registry_path.read_text(encoding="utf-8"))
    if state != REGISTRY_CANONICAL:
        raise IdentityCutoverError(
            f"{registry_path} is '{state}', not '{REGISTRY_CANONICAL}'. It is shared by "
            "every site on this bench, so fix it by hand first; preview_registry() "
            "prints the corrected text."
        )

    return {
        "installed_apps": _cutover_installed_apps(frappe),
        "module_def": _cutover_app_name(frappe, "Module Def"),
        "installed_application": _cutover_app_name(frappe, "Installed Application"),
        "dotted_paths": _cutover_dotted_paths(frappe),
    }


def _cutover_installed_apps(frappe):
    serialized = frappe.db.get_global("installed_apps")
    canonical = canonicalize_installed_apps(serialized)
    if json.loads(serialized) == canonical:
        return 0
    frappe.db.set_global("installed_apps", json.dumps(canonical))
    return 1


def _cutover_app_name(frappe, doctype):
    """Repoint one app_name-bearing doctype; returns the row count changed."""
    names = frappe.db.get_all(doctype, filters={"app_name": OLD}, pluck="name")
    for name in names:
        frappe.db.set_value(doctype, name, "app_name", NEW, update_modified=False)
    return len(names)


def _cutover_dotted_paths(frappe):
    """Rewrite the dead dotted prefix wherever a text column still stores it.

    Each column is counted before it is written, so a table with nothing to
    change is never locked and the returned evidence names only real rewrites.
    """
    if frappe.db.db_type != "mariadb":
        return _cutover_known_method_columns(frappe)

    rewritten = []
    for table, column in plan_sweep(_text_columns(frappe)):
        if not (_SAFE_IDENT.fullmatch(table) and _SAFE_IDENT.fullmatch(column)):
            continue
        hits = frappe.db.sql(
            f"SELECT COUNT(*) FROM `{table}` WHERE LOCATE(%s, `{column}`) > 0",
            (OLD_DOTTED,),
        )[0][0]
        if not hits:
            continue
        frappe.db.sql(
            f"UPDATE `{table}` SET `{column}` = REPLACE(`{column}`, %s, %s) "
            f"WHERE LOCATE(%s, `{column}`) > 0",
            (OLD_DOTTED, NEW_DOTTED, OLD_DOTTED),
        )
        rewritten.append({"table": table, "column": column, "rows": hits})
    return rewritten


def _cutover_known_method_columns(frappe):
    """Non-MariaDB fallback: heal the two config carriers this app ships rows for."""
    rewritten = []
    for doctype, field in (("Number Card", "method"), ("Scheduled Job Type", "method")):
        for row in frappe.db.get_all(doctype, fields=["name", field]):
            value = row.get(field) or ""
            if OLD_DOTTED not in value:
                continue
            frappe.db.set_value(
                doctype, row.name, field, rewrite_dotted(value), update_modified=False
            )
            rewritten.append({"table": f"tab{doctype}", "column": field, "rows": 1})
    return rewritten
