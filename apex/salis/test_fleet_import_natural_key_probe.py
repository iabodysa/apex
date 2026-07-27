# Copyright (c) 2026, AFMCO and contributors
"""A fleet master named after its DocType must still be imported.

``run`` decides whether a CSV row is already on file with ``frappe.db.exists``,
which answers the value back WITHOUT querying when it equals the DocType
(database.py:1259). A "Vehicle Category" or "Rental Office" row therefore read as
already-imported and was dropped — no insert, no count, and not even the loader's
own ``except`` path, so nothing was logged anywhere. This is the suppression
direction of the same defect the seed loader carried.

Both masters autoname by their name field, so the CSV value IS the row name: the
name filter is the correct probe and stays duplicate-safe, which the second case
pins by re-running the loader against a database that now holds the row.

Site-free: the loader's ``frappe`` is swapped for a stub that reproduces the
short-circuit faithfully; the CSVs are written to a temporary directory.
"""

import csv
import os
import tempfile
import unittest
from unittest.mock import patch

from apex.salis import fleet_import


class _StubDB:
    """``frappe.db``, faithful to database.py:1259 on the positional call shape."""

    def __init__(self, present):
        self.present = present
        self.queried = []

    def exists(self, doctype, key=None, **_kwargs):
        if isinstance(key, str) and key == doctype and doctype != "DocType":
            return key
        self.queried.append((doctype, key))
        rows = self.present.setdefault(doctype, set())
        if isinstance(key, dict):
            return next((v for v in key.values() if v in rows), None)
        return key if key in rows else None

    def get_value(self, doctype, filters, fieldname=None, **_kwargs):
        return None

    def set_value(self, *_args, **_kwargs):
        return None

    def commit(self):
        return None


class _InsertedDoc:
    def __init__(self, data, present):
        self.data = data
        self._present = present
        self.name = data.get("category_name") or data.get("office_name") or "X"

    def insert(self, **_kwargs):
        self._present.setdefault(self.data["doctype"], set()).add(self.name)
        return self


class _StubFrappe:
    def __init__(self, present=None):
        self.present = present if present is not None else {}
        self.db = _StubDB(self.present)
        self.inserted = []

    def get_doc(self, data):
        self.inserted.append(data)
        return _InsertedDoc(data, self.present)


def _write(csv_dir, filename, fieldnames, rows):
    with open(os.path.join(csv_dir, filename), "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TestSelfNamedMasterIsImported(unittest.TestCase):
    def _run(self, present=None):
        stub = _StubFrappe(present)
        with tempfile.TemporaryDirectory() as csv_dir:
            _write(
                csv_dir,
                "vehicle_category.csv",
                ["category_name", "default_fuel_type"],
                [
                    {"category_name": "Vehicle Category", "default_fuel_type": "Diesel"},
                    {"category_name": "Pickup", "default_fuel_type": "Petrol"},
                ],
            )
            _write(
                csv_dir,
                "rental_office.csv",
                ["office_name", "status"],
                [
                    {"office_name": "Rental Office", "status": "Active"},
                    {"office_name": "Riyadh Depot", "status": "Active"},
                ],
            )
            with patch.object(fleet_import, "frappe", stub):
                out = fleet_import.run(csv_dir=csv_dir)
        return out, stub

    def test_a_category_named_after_its_doctype_is_created_not_skipped(self):
        out, stub = self._run()
        self.assertEqual(out["categories_new"], 2, "the self-named row must be imported")
        self.assertIn("Vehicle Category", stub.present["Vehicle Category"])
        self.assertIn(
            ("Vehicle Category", {"name": "Vehicle Category"}),
            stub.db.queried,
            "the probe must reach the database, not short-circuit",
        )

    def test_an_office_named_after_its_doctype_is_created_not_skipped(self):
        out, stub = self._run()
        self.assertEqual(out["offices_new"], 2, "the self-named row must be imported")
        self.assertIn("Rental Office", stub.present["Rental Office"])
        self.assertIn(("Rental Office", {"name": "Rental Office"}), stub.db.queried)

    def test_a_second_run_inserts_nothing(self):
        """The duplicate-safety direction: the loader is create-only and idempotent,
        so a row already bearing that name must suppress the insert. Both masters
        autoname by their name field, so the row the first run created is exactly what
        this probe finds — a bare ``name != doctype`` rejection would re-insert it."""
        _first, stub = self._run()
        carried = {
            doctype: set(names) for doctype, names in stub.present.items()
        }
        out, second = self._run(present=carried)
        self.assertEqual(out["categories_new"], 0)
        self.assertEqual(out["offices_new"], 0)
        self.assertEqual(second.inserted, [], "an existing master must not be re-created")


if __name__ == "__main__":
    unittest.main()
