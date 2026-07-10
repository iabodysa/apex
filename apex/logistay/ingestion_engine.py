# Copyright (c) 2026, AFMCO and contributors
"""Adaptive ingestion engine for the Logistay module.

Turns heterogeneous, incomplete, multi-source, per-branch client inputs into ONE
clean canonical Timesheet Line set with per-field provenance, and records every
data-quality exception it finds in the immutable Timesheet Exception Log.

Pipeline (per pending TS Intake Source):
  parse payload -> resolve Mapping Profile -> map source tokens to canonical
  fields -> map daily status tokens via Status Code Map -> MERGE into the
  Timesheet Line keyed by (period, worker) -> gap-check the profile's required
  fields -> stamp COMPLETE/INCOMPLETE. Every gap/mismatch is logged, never
  silently dropped.

Attendance ONLY: no rates, pay or VAT are computed here (that is the owner-gated
D1-D12 rate-card / reconciliation / invoice / payroll engines). This engine
stops at canonical attendance facts + provenance + exceptions.

The single writer for the append-only exception audit trail is ``log_exception``;
the parsers and gap-check rules call it instead of inserting the log DocType.

Scheduled job:
* ``normalize_pending_intakes`` (daily) - parse + merge + gap-check every pending
  TS Intake Source. Idempotent: a source is processed once (Pending -> Processed);
  a Timesheet Line is keyed by (period, worker) so re-runs merge, never duplicate.

Intake payload contract (``TS Intake Source.ts_payload``, JSON)::

    {
      "period_month": "2026-05",            # optional, checked against the period
      "rows": [
        {
          "worker": "<Worker id or Iqama number>",
          "tokens": { "<source column>": <raw value>, ... },
          "daily": [ {"day": 1, "token": "P", "ot": 0}, ... ],   # optional
          "header_total_days": <number>                          # optional
        }
      ]
    }

An upstream extractor (per adapter) fills ``ts_payload`` from the raw upload; this
engine consumes only the structured payload, so it never parses spreadsheets.
"""

from __future__ import annotations

import json
from typing import Optional

import frappe
from frappe.utils import cint, flt, now_datetime

EXCEPTION_LOG_DOCTYPE = "Timesheet Exception Log"
INTAKE_DOCTYPE = "TS Intake Source"
LINE_DOCTYPE = "Timesheet Line"
BATCH_SIZE = 200

# Canonical Timesheet Line fields the field-map may target, with their coercion kind.
_CANONICAL_FIELDS = {
    "ts_role_package": "data",
    "ts_payable_days": "float",
    "ts_shifts": "float",
    "ts_ot_hours": "float",
    "ts_kpi_van": "float",
    "ts_kpi_pod": "float",
    "ts_kpi_success_pct": "float",
    "ts_late_ge30_days": "int",
    "ts_departure_late_count": "int",
    "ts_days_lt20_flag": "check",
    "ts_training_days": "int",
}


def log_exception(
    exception_type: str,
    entity: str,
    severity: str = "GATE",
    period_month: Optional[str] = None,
    field_ref: Optional[str] = None,
    detail: Optional[str] = None,
    source_doctype: Optional[str] = None,
    source_name: Optional[str] = None,
) -> str:
    """Append one immutable Timesheet Exception Log row. Returns its name.

    The single writer for the exception audit trail - the adapters and gap-check
    rules call this instead of inserting the log DocType directly, so there is
    one place the record shape is owned.
    """
    doc = frappe.get_doc(
        {
            "doctype": EXCEPTION_LOG_DOCTYPE,
            "exception_type": exception_type,
            "severity": severity,
            "entity": entity,
            "period_month": period_month,
            "field_ref": field_ref,
            "detail": detail,
            "detected_at": now_datetime(),
            "source_doctype": source_doctype,
            "source_name": source_name,
        }
    ).insert(ignore_permissions=True)  # audit-ok - engine logs an immutable exception row server-side
    return doc.name


# ---------------------------------------------------------------------------
# Scheduler entry point
# ---------------------------------------------------------------------------
def normalize_pending_intakes() -> int:
    """Parse + merge + gap-check every pending TS Intake Source into canonical
    Timesheet Lines. Returns the number of sources processed. Safe to re-run:
    only Pending sources are touched and lines merge on (period, worker)."""
    sources = frappe.get_all(
        INTAKE_DOCTYPE, filters={"status": "Pending"}, pluck="name", limit=BATCH_SIZE
    )
    processed = 0
    for name in sources:
        # Per-record failure isolation: a single bad intake is rolled back,
        # logged against its own record, and marked Failed so the rest of the
        # batch still runs. Narrowed from a bare ``except`` to the realistic
        # per-record data/validation failures — a genuine code or infrastructure
        # bug (AttributeError, DB OperationalError, ...) now propagates to the
        # scheduler's own job-level logging instead of being silently skipped.
        try:
            _process_source(name)
        except (frappe.ValidationError, frappe.DoesNotExistError, ValueError, TypeError, KeyError):
            frappe.db.rollback()
            frappe.log_error(
                title=f"Logistay intake failed: {name}"[:140],
                message=frappe.get_traceback(),
                reference_doctype=INTAKE_DOCTYPE,
                reference_name=name,
            )
            _fail_source(name)
        processed += 1

    if processed:
        frappe.db.commit()
    return processed


def _fail_source(name: str) -> None:
    """Mark a source Failed after an unexpected error, in its own transaction."""
    frappe.db.set_value(
        INTAKE_DOCTYPE, name, {"status": "Failed", "ts_processed_at": now_datetime()}
    )
    frappe.db.commit()


# ---------------------------------------------------------------------------
# Per-source processing
# ---------------------------------------------------------------------------
def _process_source(name: str) -> None:
    src = frappe.get_doc(INTAKE_DOCTYPE, name)
    ctx = {"rows_emitted": 0, "exceptions": 0}

    period = frappe.get_doc("Timesheet Period", src.ts_period)
    if period.status == "Closed":
        _finish(src, "Skipped", ctx, "Period is Closed - locked against ingestion.")
        return

    payload = _parse_payload(src, period, ctx)
    if payload is None:
        _finish(src, "Failed", ctx, "Payload is not machine-readable JSON.")
        return

    profile = _resolve_profile(src, period)
    if profile is None:
        _emit(
            ctx, "no_mapping_profile", src.ts_client, "GATE", period.month,
            detail="No effective Mapping Profile for this client/branch/period.",
            source_doctype=INTAKE_DOCTYPE, source_name=src.name,
        )
        _finish(src, "Skipped", ctx, "Routed to NEEDS-MAPPING: no profile matched.")
        return

    # Year/month sanity: payload's declared month must match the period.
    payload_month = (payload.get("period_month") or "").strip()
    if payload_month and payload_month != (period.month or ""):
        _emit(
            ctx, "year_month_mismatch", src.ts_client, "GATE", period.month,
            detail=f"Payload month {payload_month} != period month {period.month}.",
            source_doctype=INTAKE_DOCTYPE, source_name=src.name,
        )

    field_map = _build_field_map(profile)
    required = _build_required(profile)
    status_map = _build_status_map(profile)

    seen_workers: set = set()
    for row in payload.get("rows", []):
        _process_row(src, period, row, field_map, required, status_map, seen_workers, ctx)

    _finish(src, "Processed", ctx, f"Emitted/merged {ctx['rows_emitted']} line(s).")


def _parse_payload(src, period, ctx) -> Optional[dict]:
    raw = (src.ts_payload or "").strip()
    if not raw:
        _emit(
            ctx, "non_machine_readable_media", src.ts_client, "GATE", period.month,
            detail="Intake carries no extracted payload.",
            source_doctype=INTAKE_DOCTYPE, source_name=src.name,
        )
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        _emit(
            ctx, "non_machine_readable_media", src.ts_client, "GATE", period.month,
            detail="Payload is not valid JSON.",
            source_doctype=INTAKE_DOCTYPE, source_name=src.name,
        )
        return None
    if not isinstance(data, dict):
        return None
    return data


def _resolve_profile(src, period):
    """Explicit profile wins; else the profile in force for this client/branch at
    the period start date (effective-dated, highest version)."""
    if src.ts_mapping_profile:
        return frappe.get_doc("Mapping Profile", src.ts_mapping_profile)

    filters = {"ts_client": src.ts_client}
    if src.ts_branch_site:
        filters["ts_branch_site"] = ["in", [src.ts_branch_site, None, ""]]
    candidates = frappe.get_all(
        "Mapping Profile", filters=filters,
        fields=["name", "ts_effective_from", "ts_effective_to", "ts_version"],
        order_by="ts_version desc",
    )
    cutoff = period.start_date
    for c in candidates:
        if c.ts_effective_from and c.ts_effective_from > cutoff:
            continue
        if c.ts_effective_to and c.ts_effective_to < cutoff:
            continue
        return frappe.get_doc("Mapping Profile", c.name)
    return None


def _build_field_map(profile) -> dict:
    """source_token(lower) -> (canonical_field, transform)."""
    out = {}
    for r in profile.ts_field_map or []:
        token = (r.ts_source_token or "").strip().lower()
        if token and r.ts_canonical_field:
            out[token] = (r.ts_canonical_field, r.ts_transform or "none")
    return out


def _build_required(profile) -> dict:
    """canonical_field -> severity (GATE/WARN)."""
    out = {}
    for r in profile.ts_required_fields or []:
        if r.ts_canonical_field:
            out[r.ts_canonical_field] = r.ts_gate_severity or "GATE"
    return out


def _build_status_map(profile) -> dict:
    """source status token(lower) -> canonical status code. Global-default maps
    load first; an adapter-specific map overrides them."""
    adapter = profile.ts_adapter
    maps = frappe.get_all(
        "Status Code Map",
        filters={"enabled": 1},
        fields=["name", "ts_adapter"],
    )
    out: dict = {}
    # Global (no adapter) first, then adapter-specific overrides.
    ordered = [m for m in maps if not m.ts_adapter] + [
        m for m in maps if adapter and m.ts_adapter == adapter
    ]
    for m in ordered:
        doc = frappe.get_doc("Status Code Map", m.name)
        for row in doc.ts_token_rows or []:
            token = (row.source_token or "").strip().lower()
            if token and row.ts_status_code:
                out[token] = row.ts_status_code
    return out


def _process_row(src, period, row, field_map, required, status_map, seen_workers, ctx) -> None:
    worker = _resolve_worker(src, period, row, ctx)
    if not worker:
        return

    if worker in seen_workers:
        _emit(
            ctx, "dup_iqama", worker, "GATE", period.month,
            detail="Worker appears more than once in one intake.",
            source_doctype=INTAKE_DOCTYPE, source_name=src.name,
        )
        return
    seen_workers.add(worker)

    canonical = _map_tokens(row, field_map)
    daily = _map_daily(src, period, worker, row, status_map, ctx)
    _totals_check(src, period, worker, row, daily, ctx)

    line = _merge_line(src, period, worker, canonical, daily, ctx)
    _gate_completeness(src, period, line, required, ctx)
    line.save(ignore_permissions=True)  # audit-ok - engine writes the canonical attendance line server-side
    ctx["rows_emitted"] += 1


def _resolve_worker(src, period, row, ctx) -> Optional[str]:
    """Match an existing Worker by id, then by iqama. Never auto-creates a master."""
    key = (row.get("worker") or "").strip()
    if key and frappe.db.exists("Worker", key):
        return key
    if key:
        by_iqama = frappe.db.get_value("Worker", {"iqama_number": key}, "name")
        if by_iqama:
            return by_iqama
    _emit(
        ctx, "worker_not_found", key or "(blank)", "GATE", period.month,
        detail="No Worker matches this row's identity; register the Worker first.",
        source_doctype=INTAKE_DOCTYPE, source_name=src.name,
    )
    return None


def _map_tokens(row, field_map) -> dict:
    out = {}
    for token, value in (row.get("tokens") or {}).items():
        mapped = field_map.get((token or "").strip().lower())
        if not mapped:
            continue  # unmapped scalar columns are noise, not an exception
        canonical_field, transform = mapped
        out[canonical_field] = _coerce(canonical_field, _apply_transform(value, transform))
    return out


def _map_daily(src, period, worker, row, status_map, ctx) -> list:
    out = []
    for cell in row.get("daily") or []:
        raw = str(cell.get("token") or "").strip()
        code = status_map.get(raw.lower())
        if raw and not code:
            _emit(
                ctx, "unmapped_status_token", worker, "WARN", period.month,
                field_ref=raw, detail=f"Daily status token '{raw}' is not in any Status Code Map.",
                source_doctype=INTAKE_DOCTYPE, source_name=src.name,
            )
            continue
        if not code:
            continue
        out.append(
            {"ts_day_no": cint(cell.get("day")), "ts_status_code": code, "ts_ot_hours": flt(cell.get("ot"))}
        )
    return out


def _totals_check(src, period, worker, row, daily, ctx) -> None:
    header = row.get("header_total_days")
    if header is None or not daily:
        return
    present = sum(1 for d in daily if d["ts_status_code"] == "PRESENT")
    if flt(header) != present:
        _emit(
            ctx, "totals_vs_detail_mismatch", worker, "WARN", period.month,
            detail=f"Header total {header} != PRESENT-day count {present}.",
            source_doctype=INTAKE_DOCTYPE, source_name=src.name,
        )


def _merge_line(src, period, worker, canonical, daily, ctx):
    """Fill-if-empty merge into the one Timesheet Line for (period, worker). A
    conflicting non-empty value is kept and logged (WARN), never overwritten."""
    existing = frappe.db.exists(LINE_DOCTYPE, {"ts_period": period.name, "ts_worker": worker})
    if existing:
        line = frappe.get_doc(LINE_DOCTYPE, existing)
    else:
        line = frappe.get_doc(
            {"doctype": LINE_DOCTYPE, "ts_period": period.name, "ts_worker": worker,
             "ts_completeness": "INCOMPLETE"}
        )

    for field, value in canonical.items():
        current = line.get(field)
        if _is_empty(current):
            line.set(field, value)
            _add_provenance(line, src, field)
        elif value not in (None, "") and current != value:
            _emit(
                ctx, "merge_conflict", worker, "WARN", period.month, field_ref=field,
                detail=f"{field}: existing {current!r} kept over incoming {value!r}.",
                source_doctype=INTAKE_DOCTYPE, source_name=src.name,
            )

    if daily and not (line.ts_daily_status or []):
        for d in daily:
            line.append("ts_daily_status", d)
    return line


def _add_provenance(line, src, canonical_field) -> None:
    line.append(
        "ts_field_provenance",
        {"ts_canonical_field": canonical_field, "ts_source": src.ts_source_kind or "client_file",
         "ts_entered_by": frappe.session.user, "ts_entered_at": now_datetime()},
    )


def _gate_completeness(src, period, line, required, ctx) -> None:
    """A GATE-required field that is still empty keeps the line INCOMPLETE and
    logs a missing_field exception; otherwise the line is COMPLETE."""
    blocked = False
    for field, severity in required.items():
        if not _is_empty(line.get(field)):
            continue
        _emit(
            ctx, "missing_field", line.ts_worker, severity, period.month, field_ref=field,
            detail=f"Required field {field} is missing after merge.",
            source_doctype=INTAKE_DOCTYPE, source_name=src.name,
        )
        if severity == "GATE":
            blocked = True
    line.ts_completeness = "INCOMPLETE" if blocked else "COMPLETE"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _emit(ctx, *args, **kwargs) -> None:
    log_exception(*args, **kwargs)
    ctx["exceptions"] += 1


def _finish(src, status, ctx, note) -> None:
    src.status = status
    src.ts_processed_at = now_datetime()
    src.ts_rows_emitted = ctx["rows_emitted"]
    src.ts_exceptions_raised = ctx["exceptions"]
    src.ts_notes = note
    src.save(ignore_permissions=True)  # audit-ok - engine stamps the intake outcome server-side


def _is_empty(value) -> bool:
    return value in (None, "", 0, 0.0)


def _apply_transform(value, transform):
    if value is None:
        return value
    if transform == "trim":
        return str(value).strip()
    if transform == "strip_sci_notation":
        try:
            return flt(value)
        except (ValueError, TypeError):
            return value
    if transform == "title_parse":
        return str(value).strip().title()
    return value


def _coerce(canonical_field, value):
    kind = _CANONICAL_FIELDS.get(canonical_field, "data")
    if value is None or value == "":
        return None
    if kind == "float":
        return flt(value)
    if kind == "int":
        return cint(value)
    if kind == "check":
        return 1 if cint(value) or str(value).strip().lower() in ("true", "yes", "y") else 0
    return str(value)
