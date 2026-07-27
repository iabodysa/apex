# Copyright (c) 2026, AFMCO and contributors
"""Guards for the seed loader's existence and Link checks, including child-table rows.

``apply_spec`` used to inspect only TOP-LEVEL Link fields, so a record whose CHILD
rows pointed at missing targets passed the guard and was handed to
``doc.insert()`` — which then raised ``LinkValidationError``, because Frappe's own
``_validate_links`` DOES walk children. That is how the default Maintenance
Material Templates ended up unbuildable on a fresh install.

Site-free: ``frappe`` is replaced in ``sys.modules`` by a recording stub (the loader
imports it lazily inside the function, so the swap is seen). The stub's metadata is
read from the SHIPPED DocType JSON rather than invented, so a change to the real
child table is felt here.

The create-only contract is asserted alongside, because tightening a guard is
exactly the change that could turn a skip into a write: a record whose key already
exists must never be re-inserted, whatever its Links look like.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

from apex.apex_core.setup.seed import apply_spec

_HERE = os.path.abspath(__file__)
# Repo root: .../apex_core/setup/<this file> -> up four to the directory holding apex/.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))

_TEMPLATE = "Maintenance Material Template"
_TEMPLATE_ITEM = "Maintenance Material Template Item"
_MATERIAL = "Maintenance Material"


def _doctype_fields(doctype):
    slug = doctype.lower().replace(" ", "_")
    path = os.path.join(_REPO_ROOT, "apex", "habitat", "doctype", slug, f"{slug}.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["fields"]


class _Field(dict):
    """A DocField that answers by attribute, the way ``frappe.get_meta`` rows do."""

    def __getattr__(self, name):
        return self.get(name)


class _Meta:
    def __init__(self, fields):
        self._fields = [_Field(f) for f in fields]

    def get(self, key, filters=None):
        assert key == "fields", f"stub meta only serves 'fields', asked for {key!r}"
        rows = self._fields
        if filters:
            rows = [f for f in rows if all(f.get(k) == v for k, v in filters.items())]
        return rows

    def get_table_fields(self):
        return [f for f in self._fields if f.fieldtype in ("Table", "Table MultiSelect")]


class _StubDoc:
    def __init__(self, payload, inserted):
        self._payload = payload
        self._inserted = inserted

    def insert(self, **_kwargs):
        self._inserted.append(self._payload)


class _StubDB:
    def __init__(self, present):
        self.present = present

    def table_exists(self, doctype):
        return doctype in self.present

    def exists(self, doctype, key):
        # Faithful to database.py:1259: a POSITIONAL lookup answers the name back
        # without querying when it equals the DocType. Modelling the short-circuit is
        # what makes the self-named cases below fail against the unfixed loader; a
        # friendlier stub would have passed either way and proved nothing.
        if isinstance(key, str) and key == doctype and doctype != "DocType":
            return key
        rows = self.present.get(doctype, set())
        if isinstance(key, dict):
            return any(value in rows for value in key.values())
        return key in rows

    def savepoint(self, _name):
        return None

    def rollback(self, **_kwargs):
        return None

    def commit(self):
        return None


class _StubLogger:
    def __init__(self, warnings):
        self.warnings = warnings

    def warning(self, message):
        self.warnings.append(message)


class _StubFrappe:
    """The slice of ``frappe`` that ``apply_spec`` actually touches."""

    def __init__(self, present, metas):
        self.db = _StubDB(present)
        self._metas = metas
        self.warnings = []
        self.inserted = []
        self.errors = []

    def get_meta(self, doctype):
        return self._metas[doctype]

    def logger(self):
        return _StubLogger(self.warnings)

    def generate_hash(self, length=8):
        return "0" * length

    def get_doc(self, payload):
        return _StubDoc(payload, self.inserted)

    def log_error(self, **kwargs):
        self.errors.append(kwargs)


def _template_spec(records, create_only=True):
    return {
        "doctype": _TEMPLATE,
        "key": "template_name",
        "create_only": create_only,
        "records": records,
        "__source__": "test",
    }


_FIRE_SAFETY = {
    "template_name": "Fire Safety - Basic",
    "issue_type": "Fire Safety",
    "is_active": 1,
    "items": [
        {"material": "Fire Extinguisher", "quantity": 2},
        {"material": "Smoke Detector", "quantity": 2},
    ],
}


class _SeedLoaderCase(unittest.TestCase):
    """Shared rig: a stub frappe carrying the real template metadata."""

    def _run(self, spec, materials, templates=()):
        stub = _StubFrappe(
            present={
                _TEMPLATE: set(templates),
                _MATERIAL: set(materials),
            },
            metas={
                _TEMPLATE: _Meta(_doctype_fields(_TEMPLATE)),
                _TEMPLATE_ITEM: _Meta(_doctype_fields(_TEMPLATE_ITEM)),
            },
        )
        with patch.dict(sys.modules, {"frappe": stub}):
            counts = apply_spec(spec)
        return counts, stub


class TestChildRowLinkIsRefusedAndNamed(_SeedLoaderCase):
    def test_missing_child_target_is_skipped_and_named(self):
        counts, stub = self._run(
            _template_spec([_FIRE_SAFETY]),
            materials={"Fire Extinguisher"},
        )
        self.assertEqual(counts, {"created": 0, "skipped": 1, "failed": 0})
        self.assertEqual(stub.inserted, [], "a dangling record must never be inserted")
        self.assertEqual(len(stub.warnings), 1)
        warning = stub.warnings[0]
        self.assertIn("Smoke Detector", warning)
        self.assertIn(_MATERIAL, warning)
        self.assertIn("items row 2", warning)
        self.assertIn("Fire Safety - Basic", warning)

    def test_restoring_the_target_lets_the_record_create(self):
        counts, stub = self._run(
            _template_spec([_FIRE_SAFETY]),
            materials={"Fire Extinguisher", "Smoke Detector"},
        )
        self.assertEqual(counts, {"created": 1, "skipped": 0, "failed": 0})
        self.assertEqual(stub.warnings, [])
        self.assertEqual(len(stub.inserted), 1)
        self.assertEqual(stub.inserted[0]["template_name"], "Fire Safety - Basic")

    def test_first_unresolved_row_is_reported_not_the_last(self):
        counts, stub = self._run(_template_spec([_FIRE_SAFETY]), materials=set())
        self.assertEqual(counts["skipped"], 1)
        self.assertIn("items row 1", stub.warnings[0])
        self.assertIn("Fire Extinguisher", stub.warnings[0])

    def test_a_row_that_sets_no_link_is_not_treated_as_missing(self):
        record = dict(_FIRE_SAFETY, items=[{"quantity": 2}, {"material": None}])
        counts, stub = self._run(_template_spec([record]), materials=set())
        self.assertEqual(counts, {"created": 1, "skipped": 0, "failed": 0})
        self.assertEqual(stub.warnings, [])

    def test_a_record_with_no_child_rows_is_unaffected(self):
        record = dict(_FIRE_SAFETY)
        record.pop("items")
        counts, _ = self._run(_template_spec([record]), materials=set())
        self.assertEqual(counts, {"created": 1, "skipped": 0, "failed": 0})


class TestCreateOnlyStillHolds(_SeedLoaderCase):
    """A skip must stay a skip: the tightened Link check must not reach an
    already-present record, or a re-run would overwrite an admin's edit."""

    def test_existing_record_is_skipped_without_any_write(self):
        counts, stub = self._run(
            _template_spec([_FIRE_SAFETY]),
            materials={"Fire Extinguisher", "Smoke Detector"},
            templates={"Fire Safety - Basic"},
        )
        self.assertEqual(counts, {"created": 0, "skipped": 1, "failed": 0})
        self.assertEqual(stub.inserted, [])

    def test_existing_record_is_skipped_even_when_its_links_now_dangle(self):
        """The existence guard runs FIRST, so a material deleted after install
        cannot turn a create-only skip into a warning or a rewrite."""
        counts, stub = self._run(
            _template_spec([_FIRE_SAFETY]),
            materials=set(),
            templates={"Fire Safety - Basic"},
        )
        self.assertEqual(counts, {"created": 0, "skipped": 1, "failed": 0})
        self.assertEqual(stub.inserted, [])
        self.assertEqual(stub.warnings, [])

    def test_skip_is_counted_never_failed(self):
        counts, stub = self._run(_template_spec([_FIRE_SAFETY]), materials=set())
        self.assertEqual(counts["failed"], 0)
        self.assertEqual(stub.errors, [], "a skipped record must not raise an error log")


_NAMED = "Email Template"


class TestSelfNamedKeyIsNotReadAsAlreadySeeded(unittest.TestCase):
    """A record whose natural key equals its own DocType name must still be created.

    ``frappe.db.exists(dt, dn)`` answers ``dn`` back without querying when the two
    match, so every spec keyed on ``name`` — Email Template, Assignment Rule, Issue
    Type, Issue Priority — read such a record as already present and dropped it on
    every install. The failure is silent: no warning, no error log, just a row that
    never arrives and a ``skipped`` count that looks routine.
    """

    def _run(self, records, present):
        spec = {
            "doctype": _NAMED,
            "key": "name",
            "create_only": True,
            "records": records,
            "__source__": "test",
        }
        stub = _StubFrappe(present=present, metas={_NAMED: _Meta([])})
        with patch.dict(sys.modules, {"frappe": stub}):
            return apply_spec(spec), stub

    def test_record_named_after_its_own_doctype_is_created(self):
        counts, stub = self._run([{"name": _NAMED}], present={_NAMED: set()})
        self.assertEqual(counts, {"created": 1, "skipped": 0, "failed": 0})
        self.assertEqual([row["name"] for row in stub.inserted], [_NAMED])

    def test_that_row_is_still_skipped_once_it_really_exists(self):
        """The other direction, which a bare ``value != doctype`` rejection would
        get wrong: a real self-named row must keep its create-only protection."""
        counts, stub = self._run([{"name": _NAMED}], present={_NAMED: {_NAMED}})
        self.assertEqual(counts, {"created": 0, "skipped": 1, "failed": 0})
        self.assertEqual(stub.inserted, [])

    def test_an_ordinary_key_is_unaffected_in_both_directions(self):
        counts, _ = self._run([{"name": "Welcome Resident"}], present={_NAMED: set()})
        self.assertEqual(counts["created"], 1)
        counts, _ = self._run(
            [{"name": "Welcome Resident"}], present={_NAMED: {"Welcome Resident"}}
        )
        self.assertEqual(counts["skipped"], 1)


class TestSelfNamedLinkTargetIsCheckedAgainstTheDatabase(_SeedLoaderCase):
    """The Link probe carries the same short-circuit, in the opposite direction.

    A child row pointing at the literal string ``Maintenance Material`` cleared the
    guard without a lookup, so a dangling link was handed to ``doc.insert()``. In
    production Frappe's own ``_validate_links`` then raised, converting a clean
    skip that names the missing target into a bare ``failed`` and an error log.
    """

    def _spec(self):
        record = dict(_FIRE_SAFETY, items=[{"material": _MATERIAL, "quantity": 1}])
        return _template_spec([record])

    def test_missing_self_named_target_is_skipped_and_named(self):
        counts, stub = self._run(self._spec(), materials=set())
        self.assertEqual(counts, {"created": 0, "skipped": 1, "failed": 0})
        self.assertEqual(stub.inserted, [], "a dangling record must never be inserted")
        self.assertIn(_MATERIAL, stub.warnings[0])
        self.assertIn("items row 1", stub.warnings[0])

    def test_a_target_really_named_after_its_doctype_resolves(self):
        counts, stub = self._run(self._spec(), materials={_MATERIAL})
        self.assertEqual(counts, {"created": 1, "skipped": 0, "failed": 0})
        self.assertEqual(stub.warnings, [])


if __name__ == "__main__":
    unittest.main()
