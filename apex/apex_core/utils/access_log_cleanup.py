# Copyright (c) 2026, AFMCO and contributors
"""Size-based cleanup for oversized Frappe ``Access Log`` payload rows.

Why this is not covered by the native primitive
-----------------------------------------------
Frappe already ships the retention primitive for this table: ``Log Settings``
plus ``AccessLog.clear_old_logs(days)``, driven nightly by ``run_log_clean_up``.
That primitive is purely AGE-based - it deletes whatever is older than the
configured window and nothing else, so it cannot see a row's size.

``Access Log`` stores the *body* of what was exported, not just a reference to
it: ``frappe.utils.print_format`` writes the whole rendered print/PDF HTML into
``page``, and ``frappe.desk.reportview`` writes the full export ``columns`` and
``filters`` blobs. One bulk print therefore leaves a multi-megabyte row that is
comfortably inside the retention window, so age-based clearing keeps it for the
full window. This module adds the missing SIZE axis and nothing else: it removes
only rows whose payload columns exceed a configured byte threshold, and leaves
every normally sized audit row alone regardless of age.

Configuration (site_config.json, all optional - defaults below apply when the
key is absent or not a positive integer):

* ``apex_access_log_max_payload_bytes`` - a row is oversized when
  ``page`` + ``columns`` + ``filters`` exceed this many bytes. Default 1000000
  (1 MB); a normal Access Log row is a few hundred bytes, so only pathological
  print/export rows qualify. Raise it to effectively disable the purge.
* ``apex_access_log_purge_batch_size`` - rows deleted per statement. Default 500.
* ``apex_access_log_purge_max_batches`` - batches per run, bounding one night's
  work to ``batch_size * max_batches`` rows. Default 20 (10000 rows).

Transaction model: this job never calls ``frappe.db.commit()``. The whole run is
one transaction that the background-job wrapper commits on success, so a failure
mid-run rolls the entire purge back rather than leaving it half applied.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

DOCTYPE = "Access Log"

# The three columns that can hold an unbounded body. Access Log has no child
# table, so deleting the parent row leaves nothing orphaned.
PAYLOAD_FIELDS = ("page", "columns", "filters")

# Keys an audit record may expose: the record name and byte counts only. No
# payload body, no user, no timestamp.
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

# Selects sizes only - the payload columns are measured inside the database and
# never transferred into this process. Strictly ``>`` so a row sitting exactly on
# the threshold is preserved. Biggest rows first, so a bounded run reclaims the
# most space it can.
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
    """Read a positive integer knob from site config, else its documented default."""
    value = cint((frappe.conf or {}).get(key))
    return value if value > 0 else DEFAULTS[key]


def _sanitized_record(row: dict) -> dict:
    """Project one scan row onto the audit allowlist, so no payload body can leak
    into a return value or a log line even if the scan query later widens."""
    record = {"name": row.get("name")}
    for key in _SIZE_FIELDS:
        record[key] = cint(row.get(key))
    return record


def _scan(threshold: int, limit: int) -> list[dict]:
    rows = frappe.db.sql(SCAN_SQL, {"threshold": threshold, "limit": limit}, as_dict=True)
    return [_sanitized_record(row) for row in rows or []]


def purge_oversized_access_logs(dry_run: bool = False) -> dict:
    """Delete ``Access Log`` rows whose payload exceeds the configured byte
    threshold, in bounded batches. Registered as a nightly 23:00 cron job.

    With ``dry_run=True`` nothing is deleted and the caller gets one page of
    candidates as record names, per-field byte sizes and counts.
    """
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

    # One scan for the whole run. Measuring a column is not index-friendly, so
    # this WHERE clause costs a table scan; re-scanning per batch would pay that
    # cost once per batch. Fetching one row beyond the budget distinguishes
    # "budget exactly filled" from "more rows are still oversized".
    candidates = _scan(threshold, budget + 1)
    truncated = len(candidates) > budget
    candidates = candidates[:budget]

    deleted = 0
    freed_bytes = 0
    batches = 0

    try:
        for start in range(0, len(candidates), batch_size):
            batch = candidates[start : start + batch_size]
            # Delete by primary key only: the rows were already identified, so the
            # statement never re-reads a payload. Access Log has no child table,
            # and frappe.db.delete does not cascade, so nothing is orphaned.
            frappe.db.delete(DOCTYPE, {"name": ("in", [row["name"] for row in batch])})
            deleted += len(batch)
            freed_bytes += sum(row["payload_bytes"] for row in batch)
            batches += 1
    except Exception:
        # No commit has happened, so rolling back discards every batch of this run
        # rather than leaving a partial purge behind. Re-raised so the scheduler
        # records the failure instead of reporting a clean run.
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
