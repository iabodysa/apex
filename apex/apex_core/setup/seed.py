# Copyright (c) 2026, afmcoltd
"""Data-driven seed loader (Apex Habitat).

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

    Child rows are walked too: a Table row's Link is as fatal as a top-level one
    (Frappe's own ``_validate_links`` checks children), so a record whose rows
    dangle must be refused here rather than raising mid-batch.

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


def apply_spec(spec):
    """Create the records for one spec. Returns ``{created, skipped, failed}``.

    create-only, existence-guarded, per-record savepoint with log-then-rollback.
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
        except Exception:  # noqa: BLE001
            frappe.db.rollback(save_point=savepoint)
            frappe.log_error(title=f"seed: failed to create {doctype} '{value}'")
            failed += 1

    return {"created": created, "skipped": skipped, "failed": failed}


def seed(module_dir, only=None):
    """Load and apply every seed spec for one module. Safe to re-run.

    Wire from ``hooks.py`` ``after_install`` / ``after_migrate`` as
    ``apex.apex_core.setup.seed.seed("habitat")`` (and ``"salis"``).
    """
    import frappe

    totals = {"created": 0, "skipped": 0, "failed": 0}
    for spec in load_specs(module_dir, only=only):
        if not spec.get("apply", True):
            continue
        result = apply_spec(spec)
        for k in totals:
            totals[k] += result[k]
    frappe.db.commit()
    return totals


_MODULES = ("habitat", "salis")


def seed_all():
    """Seed every module's data files. Zero-arg hook entry for ``hooks.py``
    ``after_install`` / ``after_migrate`` — create-only, so safe on every run."""
    return {module_dir: seed(module_dir) for module_dir in _MODULES}
