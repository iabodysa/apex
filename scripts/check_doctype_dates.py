#!/usr/bin/env python3
"""DocType date/layout contract gate — semantic, not textual.

Four defects this catches that a JSON linter cannot, because each one parses fine
and only misbehaves at runtime:

1. `field_order` and `fields` disagree. Frappe renders from `field_order`, so a
   field missing from it exists in the database and is invisible on the form; a
   name in `field_order` with no field behind it is a silent no-op.
2. A start/end pair with different fieldtypes (`Date` against `Datetime`). The
   comparison in a controller then mixes a date with a timestamp and the boundary
   day behaves differently from every other day.
3. A pair rendered end-before-start. The form reads backwards and users fill it
   backwards.
4. A pair split across sections — a usability defect, not a data defect, so it is
   reported as a WARNING pending review rather than failing the lane.

Stdlib-only and self-contained ON PURPOSE: the maintainer's local toolbox is not
installable on a CI runner, so the gate has to live in the repo to run there.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_TEMPORAL = {"Date", "Datetime", "Time"}

# A pair is discovered by rewriting the opening token into its closing token and
# looking for that fieldname in the same DocType. Token pairs, not a regex on the
# whole name, so `start_odometer` never pairs with `end_date`.
_PAIR_TOKENS = (
    ("start", "end"),
    ("from", "to"),
    ("begin", "end"),
    ("issue", "expiry"),
    ("actual_start", "actual_end"),
    ("planned_start", "planned_end"),
)

_LAYOUT_BREAKS = {"Section Break", "Tab Break"}


def _partner(fieldname: str) -> str | None:
    """The fieldname this one would pair with, or None if it opens no pair."""
    parts = fieldname.split("_")
    for opener, closer in _PAIR_TOKENS:
        if "_" in opener:
            if fieldname.startswith(opener + "_"):
                return closer + fieldname[len(opener):]
            continue
        if opener in parts:
            index = parts.index(opener)
            return "_".join(parts[:index] + [closer] + parts[index + 1:])
    return None


def _section_index(order: list[str], fields: dict[str, dict], fieldname: str) -> int:
    """Which section a field renders in — the count of breaks that precede it."""
    section = 0
    for name in order:
        if name == fieldname:
            return section
        if fields.get(name, {}).get("fieldtype") in _LAYOUT_BREAKS:
            section += 1
    return -1


def scan_doctype(path: Path) -> list[dict]:
    """Findings for one DocType JSON. A `severity` of "warning" never fails."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return [{"kind": "unreadable", "severity": "error", "field": "",
                 "detail": f"cannot read the file: {type(exc).__name__}"}]
    except json.JSONDecodeError as exc:
        return [{"kind": "malformed-json", "severity": "error", "field": "",
                 "detail": f"invalid JSON at line {exc.lineno} column {exc.colno}"}]

    if not isinstance(data, dict) or data.get("doctype") != "DocType":
        return []

    raw_fields = data.get("fields")
    if not isinstance(raw_fields, list):
        return [{"kind": "malformed-json", "severity": "error", "field": "",
                 "detail": "fields is missing or not a list"}]

    fields = {f.get("fieldname"): f for f in raw_fields if isinstance(f, dict) and f.get("fieldname")}
    order = [name for name in data.get("field_order", []) if isinstance(name, str)]
    findings: list[dict] = []

    # A child table declares no field_order; only a form-rendered DocType must agree.
    if order:
        for name in sorted(set(fields) - set(order)):
            findings.append({"kind": "field-not-in-order", "severity": "error", "field": name,
                             "detail": "declared in fields but absent from field_order — invisible on the form"})
        for name in sorted(set(order) - set(fields)):
            findings.append({"kind": "order-without-field", "severity": "error", "field": name,
                             "detail": "listed in field_order with no matching field — a no-op entry"})

    for name in sorted(fields):
        field = fields[name]
        fieldtype = field.get("fieldtype")
        if fieldtype not in _TEMPORAL:
            continue
        partner_name = _partner(name)
        if not partner_name or partner_name not in fields:
            continue
        partner = fields[partner_name]
        partner_type = partner.get("fieldtype")
        if partner_type not in _TEMPORAL:
            continue
        if partner_type != fieldtype:
            findings.append({"kind": "incompatible-pair", "severity": "error", "field": name,
                             "detail": f"{name} is {fieldtype} but {partner_name} is {partner_type}"})
        if order and name in order and partner_name in order:
            if order.index(partner_name) < order.index(name):
                findings.append({"kind": "reversed-pair", "severity": "error", "field": name,
                                 "detail": f"{partner_name} renders before {name}"})
            elif _section_index(order, fields, name) != _section_index(order, fields, partner_name):
                findings.append({"kind": "pair-section-split", "severity": "warning", "field": name,
                                 "detail": f"{name} and {partner_name} render in different sections"})
    return findings


def git_files(root: Path) -> list[Path] | None:
    """DocType JSON git accounts for, or None when git cannot answer.

    Tracked plus not-yet-added, never ignored: CI audits a fresh checkout, so a
    gitignored file exists only on a developer's disk and must not be able to move
    the verdict away from what the CI lane sees.
    """
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True, check=False,
    )
    if proc.returncode != 0:
        return None
    names = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
    return [root / name for name in names if name]


def iter_doctypes(root: Path) -> list[Path]:
    candidates = git_files(root)
    if candidates is None:
        candidates = list(root.rglob("*.json"))
    return sorted(
        path for path in candidates
        if path.suffix == ".json"
        and path.parent.parent.name == "doctype"
        and path.stem == path.parent.name
        and path.is_file()
    )


def scan_tree(root: Path) -> list[dict]:
    out: list[dict] = []
    for path in iter_doctypes(root):
        for finding in scan_doctype(path):
            out.append({"file": str(path.relative_to(root)), **finding})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default="apex", help="Directory to scan")
    parser.add_argument("--json", action="store_true", help="Machine output")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    findings = scan_tree(root)
    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]

    if args.json:
        print(json.dumps({"root": str(root), "count": len(findings),
                          "error_count": len(errors), "warning_count": len(warnings),
                          "findings": findings}, ensure_ascii=False, indent=2))
        return 1 if errors else 0

    for finding in findings:
        mark = "ERROR" if finding["severity"] == "error" else "warn "
        print(f'  {mark} {finding["file"]}  [{finding["kind"]}]  {finding["detail"]}')
    print(f"doctype-dates: {len(errors)} errors, {len(warnings)} warnings")
    if errors:
        print("Fix: keep field_order and fields in agreement, give a start/end pair one "
              "fieldtype, and render the opening field first.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
