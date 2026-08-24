# Copyright (c) 2026, afmcoltd


from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count
from pypika import Order


def _constraint_exists(doctype: str, constraint_name: str) -> bool:
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
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Index add failed: {index_name}"[:140],
        )
        return False

    return _index_exists(doctype, index_name)


def add_unique_guarded(doctype: str, fields: list[str], constraint_name: str) -> bool:
    if _constraint_exists(doctype, constraint_name):
        return True

    try:
        frappe.db.add_unique(doctype, fields, constraint_name=constraint_name)
    except Exception:
        _log_blocking_duplicates(doctype, fields, constraint_name)
        return False

    return _constraint_exists(doctype, constraint_name)
