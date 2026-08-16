# Copyright (c) 2026, AFMCO and contributors
"""Guarded-index de-duplication.

Pure-Python unit tests against a fake DB — no live Frappe site needed, so they
run standalone as well as under ``bench run-tests``.

``add_index_guarded`` must recognise an EXISTING equivalent index, not just one
that happens to carry the name it was asked for. Frappe indexes a
``search_index: 1`` Link field itself, under the bare column name (table
creation) or ``<column>_index`` (later alter), so a name-only probe made the
helper create a genuine duplicate. Equivalence is EXACT ordered column-set
equality: a composite is deliberately NOT accepted as covering its leading
prefix, because Frappe's own ``get_column_index`` discards composite keys and
would still add its single-column index anyway.

Run standalone:  python3 -m unittest apex.apex_core.utils.test_guarded_index_dedupe -v
"""

import re
import sys
import types
import unittest
from unittest import mock

if "frappe" not in sys.modules:
    _fake_frappe = types.ModuleType("frappe")
    _fake_frappe.db = types.SimpleNamespace()
    _fake_frappe.qb = types.SimpleNamespace()
    _fake_frappe.log_error = lambda *a, **k: None
    _fake_frappe.get_traceback = lambda *a, **k: ""

    _fake_qb = types.ModuleType("frappe.query_builder")
    _fake_qb_functions = types.ModuleType("frappe.query_builder.functions")
    _fake_qb_functions.Count = object
    _fake_qb.functions = _fake_qb_functions
    _fake_frappe.query_builder = _fake_qb

    _fake_pypika = types.ModuleType("pypika")
    _fake_pypika.Order = types.SimpleNamespace(desc="desc", asc="asc")

    sys.modules["frappe"] = _fake_frappe
    sys.modules["frappe.query_builder"] = _fake_qb
    sys.modules["frappe.query_builder.functions"] = _fake_qb_functions
    sys.modules.setdefault("pypika", _fake_pypika)

from apex.apex_core.utils import ledger_index  # noqa: E402

_ADD_INDEX_RE = re.compile(r"ADD INDEX `([^`]+)` \((.+)\)")


class _FakeDB:
    """Minimal MariaDB stand-in that answers the two probes the helper makes.

    ``indexes`` maps index name -> ordered column list, exactly the shape
    ``SHOW INDEX`` / ``information_schema.STATISTICS`` describe. A successful
    ``ALTER TABLE ... ADD INDEX`` registers the new index, so the helper's
    post-DDL verification sees it, like a real DB would.
    """

    def __init__(self, indexes=None, fail_ddl=False):
        """Start from the given index map, optionally failing every ALTER TABLE."""
        self.indexes = dict(indexes or {})
        self.fail_ddl = fail_ddl
        self.ddl = []
        self.probes = []
        self.rollbacks = 0

    def sql(self, query, values=None, as_dict=False, **kwargs):
        """Answer the name probe, the column-set probe and the ADD INDEX statement."""
        if "SHOW INDEX" in query:
            self.probes.append((query, values))
            return [("row",)] if values and values[0] in self.indexes else []

        if "information_schema.STATISTICS" in query:
            self.probes.append((query, values))
            rows = []
            for name in sorted(self.indexes):
                for col in self.indexes[name]:
                    rows.append({"idx": name, "col": col})
            return rows

        if "ADD INDEX" in query:
            self.ddl.append(query)
            if self.fail_ddl:
                raise Exception("simulated DDL failure (bad table state)")
            match = _ADD_INDEX_RE.search(query)
            if match:
                cols = [c.strip().strip("`") for c in match.group(2).split(",")]
                self.indexes[match.group(1)] = cols
            return []

        raise AssertionError(f"unexpected query: {query}")

    def rollback(self):
        """Count a rollback, which the guarded helper must never issue."""
        self.rollbacks += 1


def _fake_frappe_ns(db):
    """The minimal ``frappe`` surface ``ledger_index`` touches, over ``db``."""
    return types.SimpleNamespace(
        db=db,
        log_error=mock.Mock(),
        get_traceback=lambda *a, **k: "traceback",
    )


class TestEquivalentIndexDetection(unittest.TestCase):
    """An equivalent index under ANY name means zero DDL."""

    def _run(self, indexes, doctype, fields, index_name):
        db = _FakeDB(indexes)
        frappe_ns = _fake_frappe_ns(db)
        with mock.patch.object(ledger_index, "frappe", frappe_ns):
            result = ledger_index.add_index_guarded(doctype, fields, index_name)
        return result, db

    def test_noop_when_frappe_search_index_already_covers_the_column(self):
        # Frappe names its search_index for `bed` either `bed` (table creation)
        # or `bed_index` (later alter) — neither is the name we ask for.
        for existing in ("bed", "bed_index"):
            with self.subTest(existing_index=existing):
                result, db = self._run(
                    {existing: ["bed"]},
                    "Housing Assignment",
                    ["bed"],
                    "idx_asgn_bed",
                )
                self.assertTrue(result)
                self.assertEqual(db.ddl, [], "helper issued DDL despite an equivalent index")

    # `test_noop_when_the_named_index_itself_exists` is not defined here: it would register
    # {"idx_asgn_bed": ["bed"]} — matching the requested NAME *and* the requested column
    # set — so with the name probe deleted the column-set probe still answers True and it
    # stays green. The case below is the same contract with only the name matching, which
    # is strictly stronger, as the sibling docstring below states.
    def test_a_name_collision_over_other_columns_is_still_a_noop(self):
        """Isolates the NAME probe, which no other test can fail on.

        The sibling tests register the index under BOTH the requested name and the
        requested column set, so with the name probe (ledger_index.py:136-144)
        deleted the column-set probe still answers True and they stay green. Here
        ONLY the name matches -- which is also the real constraint, since the engine
        refuses a second index under a name the table already carries.
        """
        result, db = self._run(
            {"idx_asgn_bed": ["room"]}, "Housing Assignment", ["bed"], "idx_asgn_bed"
        )
        self.assertTrue(result)
        self.assertEqual(
            db.ddl, [], "helper issued DDL under a name the table already carries"
        )

    def test_column_set_match_is_case_insensitive(self):
        result, db = self._run(
            {"BED_INDEX": ["BED"]}, "Housing Assignment", ["bed"], "idx_asgn_bed"
        )
        self.assertTrue(result)
        self.assertEqual(db.ddl, [])

    def test_composite_does_not_cover_its_leading_prefix(self):
        # Exact set equality, NOT leading-prefix coverage: Frappe's
        # get_column_index discards composite keys, so a composite never
        # substitutes for a single-column index.
        result, db = self._run(
            {"idx_asgn_bed_active": ["bed", "docstatus", "check_out_date"]},
            "Housing Assignment",
            ["bed"],
            "idx_asgn_bed",
        )
        self.assertTrue(result)
        self.assertEqual(len(db.ddl), 1)
        self.assertIn("ADD INDEX `idx_asgn_bed` (`bed`)", db.ddl[0])

    def test_single_column_does_not_cover_the_composite(self):
        result, db = self._run(
            {"bed_index": ["bed"]},
            "Housing Assignment",
            ["bed", "docstatus", "check_out_date"],
            "idx_asgn_bed_active",
        )
        self.assertTrue(result)
        self.assertEqual(len(db.ddl), 1)
        self.assertIn("`bed`, `docstatus`, `check_out_date`", db.ddl[0])

    def test_column_order_matters(self):
        result, db = self._run(
            {"idx_other": ["docstatus", "bed"]},
            "Housing Assignment",
            ["bed", "docstatus"],
            "idx_asgn_bed_docstatus",
        )
        self.assertTrue(result)
        self.assertEqual(len(db.ddl), 1, "(b, a) must not satisfy a request for (a, b)")

    def test_ddl_failure_still_logs_and_returns_false(self):
        db = _FakeDB({}, fail_ddl=True)
        frappe_ns = _fake_frappe_ns(db)
        with mock.patch.object(ledger_index, "frappe", frappe_ns):
            result = ledger_index.add_index_guarded("Housing Assignment", ["bed"], "idx_asgn_bed")
        self.assertFalse(result)
        # No rollback of either kind. ALTER TABLE implicitly commits in MariaDB even
        # when it fails, so the caller's work is already committed and its savepoints
        # released by the time this runs: a bare rollback would undo nothing while
        # resetting the caller's commit hooks, and a scoped one would raise
        # 1305 SAVEPOINT ... does not exist and abort the migrate.
        self.assertEqual(db.rollbacks, 0)
        frappe_ns.log_error.assert_called_once()

    def test_column_set_probe_binds_the_table_name(self):
        db = _FakeDB({})
        frappe_ns = _fake_frappe_ns(db)
        with mock.patch.object(ledger_index, "frappe", frappe_ns):
            ledger_index._column_set_indexed("Housing Assignment", ["bed"])
        query, values = db.probes[-1]
        self.assertIn("TABLE_NAME = %s", query)
        self.assertEqual(values, ("tabHousing Assignment",))
        self.assertNotIn("tabHousing Assignment", query)

    def test_probe_failure_falls_through_to_guarded_ddl(self):
        db = _FakeDB({})
        db.sql = mock.Mock(side_effect=Exception("information_schema unavailable"))
        frappe_ns = _fake_frappe_ns(db)
        with mock.patch.object(ledger_index, "frappe", frappe_ns):
            result = ledger_index.add_index_guarded("Housing Assignment", ["bed"], "idx_asgn_bed")
        self.assertFalse(result, "a probe failure must never be reported as success")
        frappe_ns.log_error.assert_called_once()


# `TestAslLedgerCallerUnchanged` is not defined here: replaying the class above's four
# claims — a per-column single missing a composite, a bare table still getting its DDL, a
# named composite staying an idempotent no-op, the same under another name — against
# ("Accommodation Stock Ledger", [is_cancelled, item_type, employee]) instead of
# ("Housing Assignment", [bed]) would duplicate those proofs, since `add_index_guarded`
# (ledger_index.py:140-172) never branches on `doctype`, only formats it into the SQL text.


if __name__ == "__main__":
    unittest.main()
