# Copyright (c) 2026, afmcoltd
"""Data-driven seed loader (Apex Habitat).

The insert passes ``ignore_permissions`` because this is installer context: the loader runs from
install and migrate as Administrator, with no session user whose roles could be consulted.

A single, minimal, create-only loader that replaces the hand-written
``*_seed.py`` modules for records whose DocType is **not** importable as
``is_standard`` module JSON — Email Template, Kanban Board, Assignment Rule,
Role, Auto Email Report, navbar links, Single defaults, and issue permissions.

(Dashboards, Dashboard Charts, Number Cards and Notifications are NOT handled
here: those DocTypes carry an ``is_standard`` field and ship as native module
JSON imported by ``bench migrate``.)

Records live as plain JSON data under ``apex_core/setup/data/<module>/<file>.json``,
one DocType per file::

    {
        "doctype": "Email Template",
        "key": "name",            # natural-key field for the existence guard
        "create_only": true,      # skip if a record with that key already exists
        "records": [ { ... }, ... ]
    }

Contract — deliberately identical to the legacy ``*_seed.py`` modules so the
switch is behaviour-preserving:

- **create-only by default**: a record matched on ``key`` is never overwritten,
  so admin edits survive both re-runs and ``bench migrate``;
- **existence-guarded**: a record is skipped (never fatal) if its DocType or any
  Link target — top-level *or* on a child row — is missing, and the log names the
  target that could not be resolved;
- **per-record savepoint + log-then-rollback**: one bad record cannot abort the
  rest (the proven pattern from the workflow / movement seeders).

``load_specs`` is intentionally free of any ``frappe`` dependency so it can be
unit-tested without a site; ``frappe`` is imported lazily inside the functions
that actually write.
"""

import json
import os

DATA_ROOT = os.path.join(os.path.dirname(__file__), "data")

_REQUIRED_KEYS = ("doctype", "key", "records")

class SeedDataError(ValueError):
    """A seed JSON file is missing a required key or is malformed."""

def load_specs(module_dir, only=None, data_root=None):
    """Read and validate every seed JSON file for one module.

    Pure function (no ``frappe``): returns a list of validated spec dicts, each
    ``{"doctype", "key", "create_only", "records", "__source__"}``.

    :param module_dir: the data sub-directory name, e.g. ``"habitat"``.
    :param only: optional iterable of DocType names to keep (others skipped).
    :param data_root: override the data root (for tests).
    """
    root = os.path.join(data_root or DATA_ROOT, module_dir)
    if not os.path.isdir(root):
        return []

    keep = set(only) if only else None
    specs = []
    for fname in sorted(os.listdir(root)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(root, fname)
        with open(path, encoding="utf-8") as fh:
            try:
                raw = json.load(fh)
            except json.JSONDecodeError as exc:
                raise SeedDataError(f"{path}: invalid JSON — {exc}") from exc

        missing = [k for k in _REQUIRED_KEYS if k not in raw]
        if missing:
            raise SeedDataError(f"{path}: missing key(s) {missing}")
        if not isinstance(raw["records"], list):
            raise SeedDataError(f"{path}: 'records' must be a list")

        if keep is not None and raw["doctype"] not in keep:
            continue

        specs.append({
            "doctype": raw["doctype"],
            "key": raw["key"],
            "create_only": raw.get("create_only", True),
            "apply": raw.get("apply", True),
            "records": raw["records"],
            "__source__": fname,
        })
    return specs

def _record_key_value(spec, record):
    """The natural-key value used for the existence guard."""
    key = spec["key"]
    if key not in record:
        raise SeedDataError(
            f"{spec['__source__']}: record missing key field '{key}'"
        )
    return record[key]

def _exists(frappe, doctype, key, value):
    """True only when a real row already carries this natural key.

    """
    if key == "name" and value != doctype:
        return bool(frappe.db.exists(doctype, value))
    return bool(frappe.db.exists(doctype, {key: value}))

def _unresolved_link(frappe, doctype, record):
    """Name the first Link target this record cannot resolve, or None if all resolve.

    Child rows are walked too: a Table row's Link is as fatal as a top-level one —
    ``Document._validate_links`` (frappe/model/document.py:969) checks children, so a
    record whose rows dangle must be refused here rather than raising mid-batch.

    ``frappe.get_meta`` (frappe/model/meta.py:66) supplies the Link fields. The one
    thing the framework's own validation cannot do is answer BEFORE the insert: it
    raises during save, which in a seed batch aborts the records that would have
    succeeded after it.
    """
    meta = frappe.get_meta(doctype)
    for field in meta.get("fields", {"fieldtype": "Link"}):
        value = record.get(field.fieldname)
        if value and field.options and not frappe.db.exists(field.options, {"name": value}):
            return f"{field.fieldname} -> {field.options} '{value}'"

    for table in meta.get_table_fields():
        child_links = frappe.get_meta(table.options).get("fields", {"fieldtype": "Link"})
        for idx, row in enumerate(record.get(table.fieldname) or [], start=1):
            if not isinstance(row, dict):
                continue
            for field in child_links:
                value = row.get(field.fieldname)
                if value and field.options and not frappe.db.exists(field.options, {"name": value}):
                    return (
                        f"{table.fieldname} row {idx}: "
                        f"{field.fieldname} -> {field.options} '{value}'"
                    )
    return None

def _linked_doctypes(frappe, doctype):
    """Every DocType this one points at through a Link, its own and its child rows'.

    Read off the schema rather than guessed: a Link field declares its target in
    ``options``, which is the same metadata ``_unresolved_link`` already reads to decide
    whether a record can be created. Dynamic Link is deliberately absent — its target is a
    value in a sibling field, so no static reading of the schema can name it.

    ``Meta.get_table_fields`` (frappe/model/meta.py:214) supplies the child tables, so
    a Link that lives only on a child row is still counted; a targets set built from
    top-level fields alone would order a parent before the DocType its rows point at.
    """
    meta = frappe.get_meta(doctype)
    targets = {f.options for f in meta.get("fields", {"fieldtype": "Link"}) if f.options}
    for table in meta.get_table_fields():
        child = frappe.get_meta(table.options)
        targets |= {f.options for f in child.get("fields", {"fieldtype": "Link"}) if f.options}
    return targets - {doctype}

def order_specs(frappe, specs):
    """Sort specs so a DocType is seeded after everything it links to.

    The order is DERIVED, not declared: seeding Room before Building fails because Room
    carries a Link to Building, and the schema already says so. Deriving it means nobody
    maintains a hand-written list that silently rots when a field is added.

    ``frappe.db.table_exists`` (frappe/database/database.py:1220) drops a DocType whose
    table is not on this site, because the order must be derivable during install when
    a later app's DocTypes do not exist yet.

    Returns ``(ordered, cyclic)``. A cycle — two DocTypes that Link to each other — cannot
    be ordered at all, so those specs come back separately for the caller's retry loop
    rather than being forced into an order that is a guess.
    """
    provided = {spec["doctype"]: spec for spec in specs}
    needs = {
        dt: _linked_doctypes(frappe, dt) & set(provided) for dt in provided if frappe.db.table_exists(dt)
    }
    ordered, placed = [], set()
    while True:
        ready = sorted(dt for dt in needs if dt not in placed and needs[dt] <= placed)
        if not ready:
            break
        for dt in ready:
            ordered.append(provided[dt])
            placed.add(dt)
    cyclic = [spec for dt, spec in provided.items() if dt not in placed]
    return ordered, cyclic

def apply_spec(spec):
    """Create the records for one spec. Returns ``{created, skipped, failed}``.

    create-only, existence-guarded, per-record savepoint with log-then-rollback.

    ``frappe.db.savepoint`` / ``rollback`` (frappe/database/database.py:1203, :1186)
    are taken PER RECORD, because the one thing a plain try/except cannot do is undo a
    partial write: a failed insert leaves child rows behind, and without a savepoint
    the next record in the batch inherits them.

    ``frappe.db.table_exists`` (frappe/database/database.py:1220) guards the whole
    spec, so a seeder that ships ahead of its DocType reports every record skipped
    rather than failing the install.
    """
    import frappe

    doctype, key = spec["doctype"], spec["key"]
    created = skipped = failed = 0

    if not frappe.db.table_exists(doctype):
        frappe.logger().warning(f"seed: DocType '{doctype}' has no table — skipped")
        return {"created": 0, "skipped": len(spec["records"]), "failed": 0}

    for record in spec["records"]:
        value = _record_key_value(spec, record)
        if spec["create_only"] and _exists(frappe, doctype, key, value):
            skipped += 1
            continue
        unresolved = _unresolved_link(frappe, doctype, record)
        if unresolved:
            frappe.logger().warning(
                f"seed: {doctype} '{value}' skipped — missing Link target {unresolved}"
            )
            skipped += 1
            continue

        savepoint = "seed_" + frappe.generate_hash(length=8)
        frappe.db.savepoint(savepoint)
        try:
            doc = frappe.get_doc({"doctype": doctype, **record})
            doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
            created += 1
        except Exception:
            frappe.db.rollback(save_point=savepoint)
            frappe.log_error(title=f"seed: failed to create {doctype} '{value}'")
            failed += 1

    return {"created": created, "skipped": skipped, "failed": failed}

def seed(module_dir, only=None):
    """Load and apply every seed spec for one module. Safe to re-run.

    Wire from ``hooks.py`` ``after_install`` / ``after_migrate`` as
    ``apex.apex_core.setup.seed.seed("habitat")`` (and ``"salis"``).

    ORDER FIRST, RETRY ONLY FOR WHAT ORDER CANNOT SEE. ``order_specs`` derives the sequence
    from the schema — a DocType is seeded after everything its Link fields point at — so
    Room follows Building because Room's own metadata says it must. What that reading
    cannot express is a Dynamic Link, whose target is a value in a sibling field, or a
    cycle; those come back as ``cyclic`` and go through the retry loop below, which repeats
    the remainder after every productive round and stops on NO PROGRESS rather than after a
    fixed number of tries, so a real defect still surfaces as a failure instead of being
    buried under repeated attempts. Frappe's own make_records
    (frappe/desk/page/setup_wizard/setup_wizard.py:504-541) does neither: it logs a failing
    record and moves on.
    """
    import frappe

    totals = {"created": 0, "skipped": 0, "failed": 0}
    specs = [spec for spec in load_specs(module_dir, only=only) if spec.get("apply", True)]
    ordered, cyclic = order_specs(frappe, specs)
    pending = ordered + cyclic
    while pending:
        progressed, still_pending = False, []
        round_totals = {"created": 0, "skipped": 0, "failed": 0}
        for spec in pending:
            result = apply_spec(spec)
            for k in round_totals:
                round_totals[k] += result[k]
            if result["created"]:
                progressed = True
            if result["skipped"] or result["failed"]:
                still_pending.append(spec)
        totals = round_totals
        if not progressed:
            break
        pending = still_pending
    frappe.db.commit()
    return totals

_MODULES = ("habitat", "salis")

def seed_all():
    """Seed every module's data files. Zero-arg hook entry for ``hooks.py``
    ``after_install`` / ``after_migrate`` — create-only, so safe on every run."""
    return {module_dir: seed(module_dir) for module_dir in _MODULES}
