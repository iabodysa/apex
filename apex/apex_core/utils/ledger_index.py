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
        col_list = ", ".join(f"`{f}`" for f in fields)
        groups = frappe.db.sql(
            """
            SELECT {cols}, COUNT(*) AS n
            FROM `tab{dt}`
            GROUP BY {cols}
            HAVING n > 1
            ORDER BY n DESC
            LIMIT 20
            """.format(cols=col_list, dt=doctype),
            as_dict=True,
        )
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


def _index_exists(doctype: str, index_name: str) -> bool:
    """True if a (plain or unique) index with this name exists on the table."""
    try:
        return bool(
            frappe.db.sql(
                "SHOW INDEX FROM `tab{dt}` WHERE Key_name = %s".format(dt=doctype),
                (index_name,),
            )
        )
    except Exception:
        return False


def add_index_guarded(doctype: str, fields: list[str], index_name: str) -> bool:
    """Add a plain composite (non-unique) performance index idempotently.

    Called from a controller ``on_doctype_update`` so BOTH fresh installs (app
    sync applies it) and existing sites (``bench migrate``) get the index — a
    patch alone never reaches fresh installs, which mark patches complete without
    running them. No-op when the index already exists; best-effort on DDL error
    (logs and returns ``False`` rather than aborting migrate).
    """
    if _index_exists(doctype, index_name):
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
