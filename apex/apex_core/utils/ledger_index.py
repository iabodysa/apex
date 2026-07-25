# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

"""Duplicate-safe composite UNIQUE index helper for the machine-written Habitat
ledgers/snapshots.

The Habitat engines (``habitat.tasks``) and submit-time hooks insert ledger,
occupancy-snapshot and scheduled-task-instance rows under an app-level
check-then-insert guard. Those guards can be defeated by a race (two scheduler
threads, an overlapping manual run), so each controller adds a composite UNIQUE
index on its natural idempotency columns via ``on_doctype_update`` — the same
hard backstop the Salis ledgers already carry.

``frappe.db.add_unique`` runs a raw ``ALTER TABLE ... ADD UNIQUE``. If the table
already holds duplicate rows for the chosen columns, MariaDB raises error 1062
and ``bench migrate`` would abort. That is unacceptable on an existing site, so
this helper:

* is a no-op when the named constraint already exists (so it is idempotent
  across repeated migrates), and
* on failure (duplicate data or any DDL error) rolls back, logs the blocking
  duplicate key groups to the Error Log, and returns ``False`` instead of
  letting the exception abort the migration.

The app-level guard remains the first line of defence; the index is the backstop
once the data is clean.
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count
from pypika import Order


def _constraint_exists(doctype: str, constraint_name: str) -> bool:
    """True if a UNIQUE constraint with this name already exists on the table."""
    try:
        return bool(
            frappe.db.sql(
                """
                SELECT CONSTRAINT_NAME
                FROM information_schema.TABLE_CONSTRAINTS
                WHERE table_name = %s
                  AND constraint_type = 'UNIQUE'
                  AND CONSTRAINT_NAME = %s
                """,
                ("tab" + doctype, constraint_name),
            )
        )
    except Exception:
        return False


def _log_blocking_duplicates(doctype: str, fields: list[str], constraint_name: str) -> None:
    """Find and log the row groups that violate the intended uniqueness, so the
    operator/orchestrator can clean them up. Best-effort: never raises."""
    try:
        tbl = frappe.qb.DocType(doctype)
        cols = [getattr(tbl, f) for f in fields]
        groups = (
            frappe.qb.from_(tbl)
            .select(*cols, Count(tbl.name).as_("n"))
            .groupby(*cols)
            .having(Count(tbl.name) > 1)
            .orderby(Count(tbl.name), order=Order.desc)
            .limit(20)
        ).run(as_dict=True)
    except Exception:
        groups = None

    detail = ""
    if groups:
        detail = "\n".join(str(dict(g)) for g in groups)

    frappe.log_error(
        message=(
            f"Could not add UNIQUE index '{constraint_name}' on "
            f"`{doctype}` ({', '.join(fields)}): the table contains duplicate "
            f"rows for these columns. Resolve the duplicates, then re-run "
            f"migrate to create the index.\n\nBlocking groups (up to 20):\n{detail}"
        ),
        title=f"UNIQUE index blocked by duplicates: {constraint_name}"[:140],
    )


def _column_set_indexed(doctype: str, fields: list[str]) -> bool:
    """True if ANY index on the table spans exactly this ordered column set.

    Frappe maintains its own single-column index for a ``search_index: 1`` field
    under a name no caller here would guess — the bare column name when the table
    is created (``frappe/database/schema.py``) or ``<column>_index`` when the
    column is indexed by a later alter (``frappe/database/mariadb/schema.py``) —
    so a name-only probe misses it and a genuine duplicate index gets created.

    EXACT ordered equality, never leading-prefix coverage: Frappe's own
    ``get_column_index`` discards composite keys (it drops any key that has a
    ``Seq_in_index = 2`` row), so a composite never satisfies the framework's
    single-column ``search_index`` and must not be treated here as covering one.
    ``(a, b)`` and ``(b, a)`` are likewise different indexes.

    Table name is BOUND, not interpolated, so no identifier reaches the SQL text.
    Best-effort: any probe failure answers "not indexed" and the caller falls
    through to its own guarded DDL.
    """
    wanted = [f.lower() for f in fields]
    by_index: dict[str, list[str]] = {}
    try:
        rows = frappe.db.sql(
            """
            SELECT INDEX_NAME AS idx, COLUMN_NAME AS col
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
            ORDER BY INDEX_NAME, SEQ_IN_INDEX
            """,
            ("tab" + doctype,),
            as_dict=True,
        )
        for row in rows or []:
            by_index.setdefault(row["idx"], []).append((row["col"] or "").lower())
    except Exception:
        return False

    return any(cols == wanted for cols in by_index.values())


def _index_exists(doctype: str, index_name: str, fields: list[str] | None = None) -> bool:
    """True if the table already carries this index.

    Matches on NAME first; when ``fields`` is given, an index over exactly that
    ordered column set counts too, whatever its name (see ``_column_set_indexed``)
    — so an equivalent index Frappe already maintains is reused, not duplicated.
    """
    try:
        named = frappe.db.sql(
            "SHOW INDEX FROM `tab{dt}` WHERE Key_name = %s".format(dt=doctype),
            (index_name,),
        )
    except Exception:
        named = None

    if named:
        return True

    return bool(fields) and _column_set_indexed(doctype, fields)


def add_index_guarded(doctype: str, fields: list[str], index_name: str) -> bool:
    """Add a plain composite (non-unique) performance index idempotently.

    Called from a controller ``on_doctype_update`` so BOTH fresh installs (app
    sync applies it) and existing sites (``bench migrate``) get the index — a
    patch alone never reaches fresh installs, which mark patches complete without
    running them. No-op when the index already exists — under ``index_name`` OR
    under any other name over the same ordered column set, so an index the
    framework already maintains is never duplicated; best-effort on DDL error
    (logs and returns ``False`` rather than aborting migrate).
    """
    # [#idxeqv] name OR equivalent column set; the post-DDL check below stays
    # name-only, since there we must confirm the index we just asked for.
    if _index_exists(doctype, index_name, fields):
        return True

    col_list = ", ".join(f"`{f}`" for f in fields)
    try:
        frappe.db.sql(
            "ALTER TABLE `tab{dt}` ADD INDEX `{idx}` ({cols})".format(
                dt=doctype, idx=index_name, cols=col_list
            )
        )
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Index add failed: {index_name}"[:140],
        )
        return False

    return _index_exists(doctype, index_name)


def add_unique_guarded(doctype: str, fields: list[str], constraint_name: str) -> bool:
    """Add a composite UNIQUE index, guarding against pre-existing duplicate data.

    Returns ``True`` if the constraint exists (already or newly created), or
    ``False`` if it could not be created (e.g. duplicate data) — in which case
    the blocking duplicate groups are logged and migration continues.
    """
    if _constraint_exists(doctype, constraint_name):
        return True

    try:
        frappe.db.add_unique(doctype, fields, constraint_name=constraint_name)
    except Exception:
        frappe.db.rollback()
        _log_blocking_duplicates(doctype, fields, constraint_name)
        return False

    # [#ouxvnt]
    return _constraint_exists(doctype, constraint_name)
