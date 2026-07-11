# Copyright (c) 2026, AFMCO and contributors
"""Registry-driven format adapters for the Logistay ingestion layer.

The ``ingestion_engine`` consumes ONE structured payload contract and never
parses spreadsheets itself (see ``ingestion_engine`` module docstring)::

    {
      "period_month": "YYYY-MM" | None,
      "rows": [
        {
          "worker": "<Worker id or Iqama number>",
          "tokens": { "<source column>": <raw value>, ... },
          "daily":  [ {"day": 1, "token": "P", "ot": 0}, ... ],
          "header_total_days": <number>          # optional
        }
      ]
    }

This module is the upstream extractor: a lookup ``adapter_code -> parser
callable`` that turns a raw tabular / keyed source into that exact contract. The
``adapter_code`` is the ``TS Format Adapter`` record name, which a Mapping
Profile links through ``ts_adapter``; so the engine's profile resolves the
adapter, and this registry resolves the parser.

GENERIC parsers only (P-197a):
* ``A``  -> ``parse_column_grid``  - a named-column tabular sheet, one row per
           worker, integer day columns become ``daily``; repeated header /
           blank rows are skipped so vertically block-stacked sheets parse.
* ``B``  -> ``parse_monthly_grid`` - a horizontal month grid: worker id column
           plus a positional day block (``day_start_column``) or integer day
           headers; leading labelled columns become ``tokens``.
* ``PAPER`` -> ``parse_paper``     - manual / keyed entry, no file parse; a list
           of row dicts (or a ``{period_month, rows}`` dict) normalised to the
           contract.

Client-specific layouts C-H are deferred to P-197b (sample-blocked) and are NOT
registered here.

Per-record isolation mirrors the engine: a malformed / identity-less row is
skipped, never raised, so one bad row cannot sink the whole batch.
"""

from __future__ import annotations

import csv
import json
import re
from typing import Callable, Optional

# adapter_code -> parser callable(source, opts) -> contract dict
_REGISTRY: dict[str, Callable] = {}

# Header cells (case-insensitive) that identify the worker column.
_WORKER_HEADERS = {
    "worker", "worker id", "iqama", "iqama_number", "iqama no", "iqama number",
    "id", "employee", "emp id", "emp_id",
}
# Header cells that identify a header-declared monthly total.
_TOTAL_HEADERS = {
    "total", "total_days", "totaldays", "total days", "header_total_days",
    "present_days", "present days",
}
_DAY_RE = re.compile(r"^[dD]?\s*(\d{1,2})$")


def register(adapter_code: str, fn: Callable) -> Callable:
    """Bind a parser callable to an adapter_code."""
    _REGISTRY[adapter_code] = fn
    return fn


def registered_codes() -> list[str]:
    return sorted(_REGISTRY)


def parse_intake(adapter_code: str, source, opts: Optional[dict] = None) -> dict:
    """Registry dispatch: run the parser bound to ``adapter_code`` and return the
    ingestion payload contract dict. Raises ValueError for an unknown code."""
    parser = _REGISTRY.get(adapter_code)
    if parser is None:
        raise ValueError(
            f"No parser registered for adapter_code {adapter_code!r}; "
            f"known: {registered_codes()}"
        )
    return parser(source, opts or {})


def build_payload_json(adapter_code: str, source, opts: Optional[dict] = None) -> str:
    """Dispatch + serialise: the JSON string to drop into ``TS Intake Source.
    ts_payload``. Pure (json only) so it is unit-testable without a site."""
    return json.dumps(parse_intake(adapter_code, source, opts), ensure_ascii=False)


# helpers
def _norm(value) -> str:
    return "" if value is None else str(value).strip()


def _day_no(header) -> Optional[int]:
    m = _DAY_RE.match(_norm(header))
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 31 else None


def _num(value):
    """Coerce a numeric-looking cell to int/float; leave non-numeric untouched."""
    try:
        f = float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return value
    return int(f) if f.is_integer() else f


def _as_matrix(source) -> list[list]:
    """Accept a pre-loaded matrix (list of rows) or a file path (.xlsx / .csv)."""
    if isinstance(source, (list, tuple)):
        return [list(row) for row in source]
    if isinstance(source, str):
        return _load_path(source)
    raise TypeError(f"Unsupported source type for a grid parser: {type(source)!r}")


def _load_path(path: str) -> list[list]:
    low = path.lower()
    if low.endswith((".xlsx", ".xlsm")):
        import openpyxl  # lazy: only needed for spreadsheet sources

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        return [list(row) for row in ws.iter_rows(values_only=True)]
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [row for row in csv.reader(fh)]


# A / B: grid parsers
def _plan(header: list[str], opts: dict, positional: bool) -> dict:
    """Classify the header row into worker / day / token / total columns."""
    worker_col = (opts.get("worker_column") or "").strip().lower()
    day_start = opts.get("day_start_column")
    worker_idx: Optional[int] = None
    day_cols: list[tuple[int, int]] = []
    token_cols: list[tuple[int, str]] = []
    total_idx: Optional[int] = None

    for i, h in enumerate(header):
        hl = _norm(h).lower()
        is_worker = (hl == worker_col) if worker_col else (hl in _WORKER_HEADERS)
        if worker_idx is None and is_worker:
            worker_idx = i
            continue
        if positional and day_start is not None and i >= day_start:
            continue  # handled positionally below
        dn = _day_no(h)
        if dn is not None:
            day_cols.append((i, dn))
        elif hl in _TOTAL_HEADERS:
            total_idx = i
        else:
            token_cols.append((i, _norm(h) or f"col{i}"))

    if worker_idx is None:
        worker_idx = 0
        token_cols = [(i, n) for (i, n) in token_cols if i != 0]
        day_cols = [(i, d) for (i, d) in day_cols if i != 0]

    if positional and day_start is not None:
        pos = 1
        for i in range(day_start, len(header)):
            if i == worker_idx:
                continue
            day_cols.append((i, pos))
            pos += 1
        day_cols.sort()

    return {
        "worker_idx": worker_idx,
        "day_cols": day_cols,
        "token_cols": token_cols,
        "total_idx": total_idx,
    }


def _record(cells: list[str], plan: dict) -> Optional[dict]:
    """One data row -> a contract row, or None to skip (per-record isolation)."""
    try:
        wi = plan["worker_idx"]
        worker = cells[wi] if wi < len(cells) else ""
        if not worker:
            return None
        tokens = {}
        for i, name in plan["token_cols"]:
            if i < len(cells) and cells[i] != "":
                tokens[name] = cells[i]
        daily = []
        for i, dn in plan["day_cols"]:
            if i < len(cells) and cells[i] != "":
                daily.append({"day": dn, "token": cells[i], "ot": 0})
        rec = {"worker": worker, "tokens": tokens, "daily": daily}
        ti = plan["total_idx"]
        if ti is not None and ti < len(cells) and cells[ti] != "":
            rec["header_total_days"] = _num(cells[ti])
        return rec
    except Exception:
        return None


def _parse_grid(source, opts: dict, positional: bool) -> dict:
    matrix = _as_matrix(source)
    period_month = opts.get("period_month")
    header: Optional[list[str]] = None
    plan: Optional[dict] = None
    rows_out: list[dict] = []
    for raw in matrix:
        cells = [_norm(c) for c in raw]
        if not any(cells):
            continue  # blank row
        if header is None:
            header = cells
            plan = _plan(header, opts, positional)
            continue
        if cells == header:
            continue  # block_stacked: a repeated header separator
        rec = _record(cells, plan)
        if rec is not None:
            rows_out.append(rec)
    return {"period_month": period_month, "rows": rows_out}


def parse_column_grid(source, opts: Optional[dict] = None) -> dict:
    """Adapter A: named-column tabular / block-stacked. Day columns are integer
    (or ``D<n>``) headers; every other labelled column becomes a token."""
    return _parse_grid(source, opts or {}, positional=False)


def parse_monthly_grid(source, opts: Optional[dict] = None) -> dict:
    """Adapter B: horizontal month grid. Pass ``day_start_column`` (0-based index)
    to map the positional day block, or rely on integer day headers."""
    return _parse_grid(source, opts or {}, positional=True)


# PAPER: manual / keyed entry (no file parse)
def _paper_record(raw) -> Optional[dict]:
    try:
        if not isinstance(raw, dict):
            return None
        worker = _norm(raw.get("worker"))
        if not worker:
            return None
        tokens = raw.get("tokens") or {}
        if not isinstance(tokens, dict):
            tokens = {}
        daily = []
        for cell in raw.get("daily") or []:
            if not isinstance(cell, dict):
                continue
            day = cell.get("day")
            token = _norm(cell.get("token"))
            if day is None or not token:
                continue
            daily.append({"day": int(day), "token": token, "ot": _num(cell.get("ot") or 0)})
        rec = {"worker": worker, "tokens": {str(k): v for k, v in tokens.items()}, "daily": daily}
        if raw.get("header_total_days") is not None:
            rec["header_total_days"] = _num(raw.get("header_total_days"))
        return rec
    except Exception:
        return None


def parse_paper(source, opts: Optional[dict] = None) -> dict:
    """Adapter PAPER: manual / keyed entry. ``source`` is a list of row dicts, or
    a ``{period_month, rows}`` dict. No file is parsed."""
    opts = opts or {}
    period_month = opts.get("period_month")
    if isinstance(source, dict):
        period_month = source.get("period_month", period_month)
        raw_rows = source.get("rows", [])
    else:
        raw_rows = source or []
    rows_out = [rec for raw in raw_rows if (rec := _paper_record(raw)) is not None]
    return {"period_month": period_month, "rows": rows_out}


# registry bindings
register("A", parse_column_grid)
register("B", parse_monthly_grid)
register("PAPER", parse_paper)


def fill_intake_payload(intake_name: str, opts: Optional[dict] = None) -> str:
    """Resolve the intake's adapter via its Mapping Profile, parse the attached
    source file, and write the payload JSON onto ``ts_payload``. Frappe is
    imported lazily so the pure parsers stay unit-testable without a site."""
    import frappe  # lazy: request-time glue only

    src = frappe.get_doc("TS Intake Source", intake_name)
    profile_name = src.ts_mapping_profile
    if not profile_name:
        raise ValueError(f"{intake_name} has no Mapping Profile to resolve an adapter.")
    adapter_code = frappe.db.get_value("Mapping Profile", profile_name, "ts_adapter")
    if not adapter_code:
        raise ValueError(f"Mapping Profile {profile_name} declares no ts_adapter.")

    if adapter_code == "PAPER":
        source = json.loads(src.ts_payload or "[]")
    else:
        if not src.ts_source_file:
            raise ValueError(f"{intake_name} has no Source File to parse.")
        source = frappe.get_doc("File", {"file_url": src.ts_source_file}).get_full_path()

    payload = build_payload_json(adapter_code, source, opts)
    frappe.db.set_value("TS Intake Source", intake_name, "ts_payload", payload)
    return payload
