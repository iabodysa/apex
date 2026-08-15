# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for habitat/tasks scheduler functions.

These need frappe IMPORTABLE, not a live site. ``TestWeeklyOccupancySyncEmptyBuilding``
drives the SHIPPED ``occupancy.weekly_occupancy_sync`` with only its database edges
stubbed, and ``TestDeadBeforeSaveGuardsRemoved`` imports the real controller modules.
The latter used to swallow an ImportError into a ``skipTest``, which turned "the
controllers no longer import" — a genuine breakage — into a green run, so the import
is now allowed to fail loudly.: the occupancy class used to REIMPLEMENT the building pass it claimed to cover —
a local copy of production's loop, asserted against itself — so
``weekly_occupancy_sync`` was deletable with every test in this file still green. That
is worse than no coverage, because it looks like coverage. It now calls the real
function; the skip condition under test is production's own, and deleting it or
inverting it reds the tests. ``TestLedgerTypeOptions`` had the same defect one layer
over: it compared two hand-maintained copies of Select options with each other, so
dropping an option from either shipped DocType JSON left it green. It reads the JSON.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

import apex
from apex.habitat.tasks import occupancy

_HABITAT = os.path.join(str(Path(apex.__file__).resolve().parent), "habitat")


class _Column:
    """One stubbed query-builder column.

    Every operator the pass applies to a column returns the column itself: the
    predicates are never rendered, because only the GROUPBY is read back (see
    ``_Query.run``), so a faithful expression tree would be cost with no signal.
    """

    def __init__(self, fieldname):
        self.fieldname = fieldname

    def isnull(self):
        return self

    def isnotnull(self):
        return self

    def __eq__(self, other):
        return self

    def __or__(self, other):
        return self

    __ror__ = __or__

    def __hash__(self):
        return id(self)


class _Table:
    def __init__(self, doctype):
        self.doctype = doctype
        self.columns = {}

    def __getattr__(self, fieldname):
        return self.columns.setdefault(fieldname, _Column(fieldname))


class _Query:
    """Chainable no-op builder whose ``run`` answers from the fixture.

    Keyed on ``(from-doctype, groupby fieldnames)`` because that pair is what tells
    ``weekly_occupancy_sync``'s three grouped reads apart — two of them select FROM
    the same Housing Assignment table and differ only in what they group by.
    """

    def __init__(self, table, grouped):
        self._table = table
        self._grouped = grouped
        self._groupby = ()

    def select(self, *args, **kwargs):
        return self

    def where(self, *args, **kwargs):
        return self

    def groupby(self, *columns):
        self._groupby += tuple(column.fieldname for column in columns)
        return self

    def run(self, as_dict=False):
        return self._grouped.get((self._table.doctype, self._groupby), [])


class _QueryBuilder:
    def __init__(self, grouped):
        self._grouped = grouped
        self._tables = {}

    # Capitalised to mirror frappe.qb.DocType, which is what production calls.
    def DocType(self, doctype):
        return self._tables.setdefault(doctype, _Table(doctype))

    def from_(self, table):
        return _Query(table, self._grouped)


class _FakeDB:
    """Records the savepoint traffic, because that is now part of the contract.

    The fake previously offered a no-arg ``rollback`` and no ``savepoint`` at all,
    which is the shape of the bug: it could only model an all-or-nothing recovery.
    """

    def __init__(self):
        self.writes = {}
        self.savepoints = []
        self.rollbacks = []

    def set_value(self, doctype, name, values, update_modified=True):
        self.writes.setdefault(doctype, {})[name] = dict(values)

    def savepoint(self, save_point):
        self.savepoints.append(save_point)

    def rollback(self, save_point=None):
        self.rollbacks.append(save_point)


class _FakeFrappe:
    """Exactly the frappe surface ``weekly_occupancy_sync`` itself touches.

    ``log_error`` RECORDS instead of discarding: production wraps each building in a
    try/except that logs and continues, so a building skipped by the guard under test
    and a building whose write blew up are indistinguishable in the output unless the
    swallowed error is surfaced.
    """

    def __init__(self, rows, grouped):
        self.qb = _QueryBuilder(grouped)
        self.db = _FakeDB()
        self.rows = rows
        self.errors = []

    def get_all(self, doctype, fields=None, limit_start=0, limit_page_length=0, **kwargs):
        page = self.rows.get(doctype, [])
        return page[limit_start : limit_start + limit_page_length]

    def log_error(self, message=None, title=None):
        self.errors.append(title or message)

    def get_traceback(self):
        return ""

    def logger(self):
        return SimpleNamespace(info=lambda *args, **kwargs: None)


class TestWeeklyOccupancySyncEmptyBuilding(unittest.TestCase):
    """Finding 2: the SHIPPED weekly_occupancy_sync must not divide by zero or
    crash when a building has no rooms assigned."""

    def _run_sync_building_pass(self, buildings, room_counts, active_counts, capacities):
        """Drive the real ``weekly_occupancy_sync`` and return what it wrote per building.

        Only the database edges are replaced — the query builder, ``get_all`` and
        ``db.set_value`` — so the loop, the arithmetic and the zero-room skip are
        production's. No Room rows are offered, so the room pass runs zero iterations
        and the building pass is what this class exercises.
        """
        fake = _FakeFrappe(
            rows={
                "Building": [
                    SimpleNamespace(name=b, total_capacity=capacities.get(b, 0))
                    for b in buildings
                ]
            },
            grouped={
                ("Room", ("building",)): [
                    {"building": b, "n": room_counts.get(b, 0)} for b in buildings
                ],
                ("Housing Assignment", ("building",)): [
                    {"building": b, "n": active_counts.get(b, 0)} for b in buildings
                ],
            },
        )
        with mock.patch.object(occupancy, "frappe", fake):
            occupancy.weekly_occupancy_sync()
        self.assertEqual(
            fake.errors,
            [],
            "the pass swallowed an exception, so a 'skipped' building may really be a "
            "crashed one",
        )
        return fake.db.writes.get("Building", {})

    def test_empty_building_skipped(self):
        """A building with zero rooms must be skipped without raising ZeroDivisionError."""
        buildings = ["BLDG-EMPTY", "BLDG-NORMAL"]
        room_counts = {"BLDG-EMPTY": 0, "BLDG-NORMAL": 5}
        active_counts = {"BLDG-EMPTY": 0, "BLDG-NORMAL": 3}
        capacities = {"BLDG-EMPTY": 0, "BLDG-NORMAL": 20}

        results = self._run_sync_building_pass(buildings, room_counts, active_counts, capacities)

        self.assertNotIn("BLDG-EMPTY", results, "Empty building should be skipped.")
        self.assertIn("BLDG-NORMAL", results)
        self.assertEqual(results["BLDG-NORMAL"]["current_occupants"], 3)
        self.assertAlmostEqual(results["BLDG-NORMAL"]["occupancy_percent"], 15.0)

    def test_zero_capacity_building_does_not_divide(self):
        """A building with rooms but zero total_capacity must produce 0.0 occupancy_percent."""
        buildings = ["BLDG-NO-CAP"]
        room_counts = {"BLDG-NO-CAP": 2}
        active_counts = {"BLDG-NO-CAP": 1}
        capacities = {"BLDG-NO-CAP": 0}

        results = self._run_sync_building_pass(buildings, room_counts, active_counts, capacities)

        self.assertIn("BLDG-NO-CAP", results)
        self.assertEqual(results["BLDG-NO-CAP"]["occupancy_percent"], 0.0)

    def test_fully_occupied_building(self):
        """A fully occupied building should show 100% occupancy."""
        buildings = ["BLDG-FULL"]
        room_counts = {"BLDG-FULL": 10}
        active_counts = {"BLDG-FULL": 20}
        capacities = {"BLDG-FULL": 20}

        results = self._run_sync_building_pass(buildings, room_counts, active_counts, capacities)

        self.assertIn("BLDG-FULL", results)
        self.assertAlmostEqual(results["BLDG-FULL"]["occupancy_percent"], 100.0)

    def test_the_harness_reaches_the_shipped_pass_and_not_a_copy(self):
        """Non-vacuous: an empty result set satisfies every assertNotIn above.

        Deleting ``weekly_occupancy_sync`` or inverting its ``if not total_rooms``
        skip must red this class, which it cannot do if the harness quietly writes
        nothing at all. So assert the pass WROTE, through production's own writer.
        """
        results = self._run_sync_building_pass(
            ["BLDG-PROOF"], {"BLDG-PROOF": 1}, {"BLDG-PROOF": 2}, {"BLDG-PROOF": 4}
        )

        self.assertEqual(
            results,
            {"BLDG-PROOF": {"current_occupants": 2, "occupancy_percent": 50.0}},
        )

    def test_one_failed_building_does_not_discard_the_buildings_already_written(self):
        """The recovery must be row-scoped, not all-or-nothing.

        The loop CONTINUES past a failure, so a bare ``frappe.db.rollback()`` would
        throw away every building the run had already counted. Assert the failing row
        rolls back to a NAMED savepoint (so the surviving rows are untouched) and that
        the run reaches the building after the failure.
        """
        buildings = ["BLDG-BEFORE", "BLDG-BOOM", "BLDG-AFTER"]
        fake = _FakeFrappe(
            rows={"Building": [SimpleNamespace(name=b, total_capacity=10) for b in buildings]},
            grouped={
                ("Room", ("building",)): [{"building": b, "n": 2} for b in buildings],
                ("Housing Assignment", ("building",)): [{"building": b, "n": 5} for b in buildings],
            },
        )
        good = fake.db.set_value

        def _boom(doctype, name, values, update_modified=True):
            if name == "BLDG-BOOM":
                raise RuntimeError("write failed")
            good(doctype, name, values, update_modified=update_modified)

        fake.db.set_value = _boom
        with mock.patch.object(occupancy, "frappe", fake):
            occupancy.weekly_occupancy_sync()

        written = fake.db.writes.get("Building", {})
        self.assertIn("BLDG-BEFORE", written, "the row written before the failure was discarded")
        self.assertIn("BLDG-AFTER", written, "the loop stopped reaching rows after the failure")
        self.assertNotIn("BLDG-BOOM", written)
        self.assertEqual(
            fake.db.rollbacks,
            [occupancy._ROW_SAVEPOINT],
            "recovery must roll back to the row savepoint, never the whole transaction",
        )
        self.assertIn(occupancy._ROW_SAVEPOINT, fake.db.savepoints)
        self.assertEqual(len(fake.errors), 1)


def _select_options(doctype_slug, fieldname):
    """The Select options one SHIPPED habitat DocType JSON declares for a field."""
    path = os.path.join(_HABITAT, "doctype", doctype_slug, doctype_slug + ".json")
    with open(path, encoding="utf-8") as fh:
        meta = json.load(fh)
    for field in meta.get("fields", []):
        if field.get("fieldname") == fieldname:
            return [o for o in (field.get("options") or "").split("\n") if o]
    raise AssertionError(f"{doctype_slug}.{fieldname} no longer exists — repair this test")


class TestLedgerTypeOptions(unittest.TestCase):
    """Finding 1: Accommodation Ledger ledger_type must include every Utility Account
    utility_type value — read off the shipped JSON, never a copy kept here.

    Both sets used to be hand-maintained constants in this file compared with each
    other, so dropping Gas from either DocType left the class green: the defect
    one layer over, a test asserting against its own copy of production.
    """

    def setUp(self):
        self.ledger_types = _select_options("accommodation_ledger", "ledger_type")
        self.utility_types = _select_options("utility_account", "utility_type")

    def test_the_shipped_options_are_really_read(self):
        """Non-vacuous: an empty read would satisfy the subset check trivially."""
        self.assertIn("Rent", self.ledger_types)
        self.assertIn("Other", self.ledger_types)
        self.assertGreater(len(self.utility_types), 3)

    def test_all_utility_types_covered_by_ledger_type(self):
        """Every utility_type value must be a valid ledger_type option."""
        missing = sorted(set(self.utility_types) - set(self.ledger_types))
        self.assertEqual(
            missing,
            [],
            f"utility_type values not in ledger_type options: {missing}",
        )

    def test_json_options_contain_gas(self):
        """Gas must be in the ledger_type options."""
        self.assertIn("Gas", self.ledger_types)

    def test_json_options_contain_internet(self):
        """Internet must be in the ledger_type options."""
        self.assertIn("Internet", self.ledger_types)

    def test_json_options_contain_telecom(self):
        """Telecom must be in the ledger_type options."""
        self.assertIn("Telecom", self.ledger_types)


class TestDeadBeforeSaveGuardsRemoved(unittest.TestCase):
    """Finding 4: dead before_save guards that check self.doctype != "..." have been removed."""

    def _get_before_save(self, module_path, class_name):
        """Import a controller module and return its before_save method if present.

        An ImportError is deliberately allowed to propagate: a controller module
        that no longer imports is a failure, not a reason to report success.
        """
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name, None)
        self.assertIsNotNone(cls, f"{class_name} missing from {module_path}")
        return getattr(cls, "before_save", None)

    def _assert_no_dead_doctype_guard(self, module_path, class_name):
        # Either the controller has no before_save at all (the intended end
        # state), or it has one that no longer carries the dead doctype-mismatch throw.
        bs = self._get_before_save(module_path, class_name)
        if bs is None:
            return
        self.assertNotIn('frappe.throw("DocType mismatch")', inspect.getsource(bs))

    def test_accommodation_custody_item_has_no_before_save(self):
        """AccommodationCustodyItem must not define a dead before_save guard."""
        self._assert_no_dead_doctype_guard(
            "apex.habitat.doctype.accommodation_custody_item.accommodation_custody_item",
            "AccommodationCustodyItem",
        )

    def test_maintenance_work_order_has_no_dead_guard(self):
        """MaintenanceWorkOrder must not have a dead doctype-mismatch guard in before_save."""
        self._assert_no_dead_doctype_guard(
            "apex.habitat.doctype.maintenance_work_order.maintenance_work_order",
            "MaintenanceWorkOrder",
        )


if __name__ == "__main__":
    unittest.main()
