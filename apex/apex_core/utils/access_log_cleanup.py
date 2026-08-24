# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils import cint

DOCTYPE = "Access Log"

PAYLOAD_FIELDS = ("page", "columns", "filters")

AUDIT_FIELDS = ("name", "page_bytes", "columns_bytes", "filters_bytes", "payload_bytes")

_SIZE_FIELDS = AUDIT_FIELDS[1:]

DEFAULTS = {
    "apex_access_log_max_payload_bytes": 1000000,
    "apex_access_log_purge_batch_size": 500,
    "apex_access_log_purge_max_batches": 20,
}

_PAYLOAD_BYTES = (
    "COALESCE(OCTET_LENGTH(`page`), 0) "
    "+ COALESCE(OCTET_LENGTH(`columns`), 0) "
    "+ COALESCE(OCTET_LENGTH(`filters`), 0)"
)

SCAN_SQL = f"""
    SELECT
        `name`,
        COALESCE(OCTET_LENGTH(`page`), 0) AS page_bytes,
        COALESCE(OCTET_LENGTH(`columns`), 0) AS columns_bytes,
        COALESCE(OCTET_LENGTH(`filters`), 0) AS filters_bytes,
        {_PAYLOAD_BYTES} AS payload_bytes
    FROM `tabAccess Log`
    WHERE {_PAYLOAD_BYTES} > %(threshold)s
    ORDER BY payload_bytes DESC, `name` ASC
    LIMIT %(limit)s
"""


def _setting(key: str) -> int:
    value = cint((frappe.conf or {}).get(key))
    return value if value > 0 else DEFAULTS[key]


def _sanitized_record(row: dict) -> dict:
    record = {"name": row.get("name")}
    for key in _SIZE_FIELDS:
        record[key] = cint(row.get(key))
    return record


def _scan(threshold: int, limit: int) -> list[dict]:
    rows = frappe.db.sql(SCAN_SQL, {"threshold": threshold, "limit": limit}, as_dict=True)
    return [_sanitized_record(row) for row in rows or []]


def purge_oversized_access_logs(dry_run: bool = False) -> dict:
    threshold = _setting("apex_access_log_max_payload_bytes")
    batch_size = _setting("apex_access_log_purge_batch_size")
    result = {"threshold_bytes": threshold, "batch_size": batch_size, "dry_run": bool(dry_run)}

    if dry_run:
        candidates = _scan(threshold, batch_size)
        result["count"] = len(candidates)
        result["total_bytes"] = sum(row["payload_bytes"] for row in candidates)
        result["records"] = candidates
        return result

    max_batches = _setting("apex_access_log_purge_max_batches")
    budget = batch_size * max_batches

    candidates = _scan(threshold, budget + 1)
    truncated = len(candidates) > budget
    candidates = candidates[:budget]

    deleted = 0
    freed_bytes = 0
    batches = 0

    try:
        for start in range(0, len(candidates), batch_size):
            batch = candidates[start : start + batch_size]
            frappe.db.delete(DOCTYPE, {"name": ("in", [row["name"] for row in batch])})
            deleted += len(batch)
            freed_bytes += sum(row["payload_bytes"] for row in batch)
            batches += 1
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="Access Log oversized payload purge failed",
            message=f"Deleted {deleted} row(s) in {batches} batch(es) before failing; rolled back.",
        )
        raise

    result.update(
        {
            "max_batches": max_batches,
            "batches": batches,
            "deleted": deleted,
            "freed_bytes": freed_bytes,
            "truncated": truncated,
        }
    )
    frappe.logger("apex").info(
        f"Access Log purge: deleted {deleted} oversized row(s) "
        f"({freed_bytes} bytes) in {batches} batch(es) above {threshold} bytes."
    )
    return result
