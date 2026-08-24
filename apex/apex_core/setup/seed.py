# Copyright (c) 2026, afmcoltd

import json
import os

import frappe

DATA_ROOT = os.path.join(os.path.dirname(__file__), "data")

_REQUIRED_KEYS = ("doctype", "key", "records")

class SeedDataError(ValueError):
    pass

def load_specs(module_dir, only=None, data_root=None):
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
    key = spec["key"]
    if key not in record:
        raise SeedDataError(
            f"{spec['__source__']}: record missing key field '{key}'"
        )
    return record[key]

def _exists(frappe, doctype, key, value):
    if key == "name" and value != doctype:
        return bool(frappe.db.exists(doctype, value))
    return bool(frappe.db.exists(doctype, {key: value}))

def _unresolved_link(frappe, doctype, record):
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
    meta = frappe.get_meta(doctype)
    targets = {f.options for f in meta.get("fields", {"fieldtype": "Link"}) if f.options}
    for table in meta.get_table_fields():
        child = frappe.get_meta(table.options)
        targets |= {f.options for f in child.get("fields", {"fieldtype": "Link"}) if f.options}
    return targets - {doctype}

def order_specs(frappe, specs):
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
    doctype, key = spec["doctype"], spec["key"]
    created = skipped = failed = 0

    if not frappe.db.table_exists(doctype):
        print(f"apex: seed skipped — DocType '{doctype}' has no table")
        return {"created": 0, "skipped": len(spec["records"]), "failed": 0}

    for record in spec["records"]:
        value = _record_key_value(spec, record)
        if spec["create_only"] and _exists(frappe, doctype, key, value):
            skipped += 1
            continue
        unresolved = _unresolved_link(frappe, doctype, record)
        if unresolved:
            print(
                f"apex: seed skipped — {doctype} '{value}' is missing Link target {unresolved}"
            )
            skipped += 1
            continue

        savepoint = "seed_" + frappe.generate_hash(length=8)
        frappe.db.savepoint(savepoint)
        try:
            doc = frappe.get_doc({"doctype": doctype, **record})
            doc.insert(ignore_if_duplicate=True)
            created += 1
        except Exception:
            frappe.db.rollback(save_point=savepoint)
            frappe.log_error(title=f"seed: failed to create {doctype} '{value}'")
            failed += 1

    return {"created": created, "skipped": skipped, "failed": failed}

def seed(module_dir, only=None):
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
    return {module_dir: seed(module_dir) for module_dir in _MODULES}
