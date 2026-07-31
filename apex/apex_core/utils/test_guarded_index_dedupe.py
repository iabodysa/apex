# Copyright (c) 2026, AFMCO and contributors
"""Guarded-index de-duplication + bed-index patch delegation (A-128 / A-129).

Pure-Python unit tests against a fake DB — no live Frappe site needed, so they
run standalone as well as under ``bench run-tests``.

A-129 — ``add_index_guarded`` must recognise an EXISTING equivalent index, not
just one that happens to carry the name it was asked for. Frappe indexes a
``search_index: 1`` Link field itself, under the bare column name (table
creation) or ``<column>_index`` (later alter), so a name-only probe made the
helper create a genuine duplicate. Equivalence is EXACT ordered column-set
equality: a composite is deliberately NOT accepted as covering its leading
prefix, because Frappe's own ``get_column_index`` discards composite keys and
would still add its single-column index anyway.

A-128 — ``apex.patches.v0_7.add_bed_assignment_index`` must delegate to that
helper instead of issuing raw ``ALTER TABLE`` that re-raises: a bad table state
on a site where the patch has genuinely not run yet used to abort the entire
``bench migrate``. Failure must now log and continue.

Run standalone:  python3 -m unittest apex.apex_core.utils.test_guarded_index_dedupe -v
"""

import re
import sys
import types
import unittest
from unittest import mock

# [#idxstb] Same stubbing idiom as tests/test_worker_party.py: import the real
# frappe when running under bench, otherwise stand up the minimum surface the
# modules under test import at module scope, so this file is runnable standalone.
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

    # Since the patch delegates to the controller, execute() drags in
    # housing_assignment and its imports; these exist only to let that chain
    # import, never to behave — every test patches the frappe it actually calls.
    _fake_frappe._ = lambda msg, *a, **k: msg

    _fake_model = types.ModuleType("frappe.model")
    _fake_document = types.ModuleType("frappe.model.document")
    _fake_document.Document = type("Document", (), {})
    _fake_model.document = _fake_document
    _fake_frappe.model = _fake_model

    _fake_utils = types.ModuleType("frappe.utils")
    _fake_utils.flt = lambda value, *a, **k: float(value or 0)
    _fake_utils.today = lambda: "1970-01-01"
    _fake_frappe.utils = _fake_utils

    sys.modules["frappe"] = _fake_frappe
    sys.modules["frappe.query_builder"] = _fake_qb
    sys.modules["frappe.query_builder.functions"] = _fake_qb_functions
    sys.modules["frappe.model"] = _fake_model
    sys.modules["frappe.model.document"] = _fake_document
    sys.modules["frappe.utils"] = _fake_utils
    sys.modules.setdefault("pypika", _fake_pypika)

from apex.apex_core.utils import ledger_index  # noqa: E402
from apex.patches.v0_7 import add_bed_assignment_index  # noqa: E402

_ADD_INDEX_RE = re.compile(r"ADD INDEX `([^`]+)` \((.+)\)")


class _FakeDB:
    """Minimal MariaDB stand-in that answers the two probes the helper makes.

    ``indexes`` maps index name -> ordered column list, exactly the shape
    ``SHOW INDEX`` / ``information_schema.STATISTICS`` describe. A successful
    ``ALTER TABLE ... ADD INDEX`` registers the new index, so the helper's
    post-DDL verification sees it, like a real DB would.
    """

    def __init__(self, indexes=None, fail_ddl=False):
        self.indexes = dict(indexes or {})
        self.fail_ddl = fail_ddl
        self.ddl = []
        self.probes = []
        self.commits = 0
        self.rollbacks = 0

    def sql(self, query, values=None, as_dict=False, **kwargs):
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

    def exists(self, *args, **kwargs):
        return True

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _fake_frappe_ns(db):
    return types.SimpleNamespace(
        db=db,
        log_error=mock.Mock(),
        get_traceback=lambda *a, **k: "traceback",
    )


class TestEquivalentIndexDetection(unittest.TestCase):
    """A-129: an equivalent index under ANY name means zero DDL."""

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

    def test_noop_when_the_named_index_itself_exists(self):
        result, db = self._run(
            {"idx_asgn_bed": ["bed"]}, "Housing Assignment", ["bed"], "idx_asgn_bed"
        )
        self.assertTrue(result)
        self.assertEqual(db.ddl, [])

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


class TestAslLedgerCallerUnchanged(unittest.TestCase):
    """A-129: the pre-existing ASL caller keeps its exact behaviour."""

    ARGS = ("Accommodation Stock Ledger", ["is_cancelled", "item_type", "employee"])
    NAME = "idx_asl_cancel_type_emp"

    def _run(self, indexes):
        db = _FakeDB(indexes)
        frappe_ns = _fake_frappe_ns(db)
        with mock.patch.object(ledger_index, "frappe", frappe_ns):
            result = ledger_index.add_index_guarded(*self.ARGS, self.NAME)
        return result, db

    def test_per_column_search_indexes_do_not_suppress_the_composite(self):
        result, db = self._run(
            {
                "is_cancelled": ["is_cancelled"],
                "item_type_index": ["item_type"],
                "employee_index": ["employee"],
            }
        )
        self.assertTrue(result)
        self.assertEqual(len(db.ddl), 1, "widened check must not skip the ASL composite")
        self.assertIn("ADD INDEX `idx_asl_cancel_type_emp`", db.ddl[0])
        self.assertIn("`is_cancelled`, `item_type`, `employee`", db.ddl[0])

    def test_composite_on_a_bare_table_is_still_created(self):
        result, db = self._run({})
        self.assertTrue(result)
        self.assertEqual(len(db.ddl), 1)

    def test_named_composite_is_still_an_idempotent_noop(self):
        result, db = self._run({self.NAME: ["is_cancelled", "item_type", "employee"]})
        self.assertTrue(result)
        self.assertEqual(db.ddl, [])

    def test_same_composite_under_another_name_is_now_reused(self):
        result, db = self._run({"idx_legacy_asl": ["is_cancelled", "item_type", "employee"]})
        self.assertTrue(result)
        self.assertEqual(db.ddl, [], "an identical composite must not be duplicated")


class TestBedAssignmentIndexPatch(unittest.TestCase):
    """A-128: the patch delegates and never aborts migrate."""

    def _execute(self, db):
        frappe_ns = _fake_frappe_ns(db)
        with mock.patch.object(add_bed_assignment_index, "frappe", frappe_ns), \
             mock.patch.object(ledger_index, "frappe", frappe_ns):
            returned = add_bed_assignment_index.execute()
        return returned, frappe_ns

    def test_execute_returns_when_the_ddl_raises(self):
        # Forced DDL failure: execute() must RETURN, not propagate — a raise
        # here aborts the whole bench migrate.
        db = _FakeDB({}, fail_ddl=True)
        returned, frappe_ns = self._execute(db)
        self.assertIsNone(returned)
        self.assertEqual(len(db.ddl), 2, "both indexes must still be attempted")
        # Neither failed index rolls anything back — see the note on
        # test_ddl_failure_still_logs_and_returns_false. A rollback here would have
        # discarded whatever the migrate did before this patch ran.
        self.assertEqual(db.rollbacks, 0)
        self.assertEqual(frappe_ns.log_error.call_count, 2)
        self.assertEqual(db.commits, 1, "the patch must still finish cleanly")

    def test_execute_creates_both_indexes_on_a_bare_table(self):
        db = _FakeDB({})
        returned, _ = self._execute(db)
        self.assertIsNone(returned)
        self.assertEqual(sorted(db.indexes), ["idx_asgn_bed", "idx_asgn_bed_active"])
        self.assertEqual(db.indexes["idx_asgn_bed"], ["bed"])
        self.assertEqual(
            db.indexes["idx_asgn_bed_active"], ["bed", "docstatus", "check_out_date"]
        )

    def test_execute_is_idempotent_on_an_already_migrated_site(self):
        db = _FakeDB(
            {
                "idx_asgn_bed": ["bed"],
                "idx_asgn_bed_active": ["bed", "docstatus", "check_out_date"],
            }
        )
        returned, frappe_ns = self._execute(db)
        self.assertIsNone(returned)
        self.assertEqual(db.ddl, [])
        frappe_ns.log_error.assert_not_called()

    def test_execute_delegates_to_the_guarded_helper(self):
        db = _FakeDB({})
        frappe_ns = _fake_frappe_ns(db)
        with mock.patch.object(add_bed_assignment_index, "frappe", frappe_ns), \
             mock.patch.object(ledger_index, "add_index_guarded") as guarded:
            add_bed_assignment_index.execute()
        self.assertEqual(
            [call.args for call in guarded.call_args_list],
            [
                ("Housing Assignment", ["bed"], "idx_asgn_bed"),
                (
                    "Housing Assignment",
                    ["bed", "docstatus", "check_out_date"],
                    "idx_asgn_bed_active",
                ),
            ],
        )
        self.assertEqual(db.ddl, [], "the patch must issue no DDL of its own")

    def test_execute_skips_when_the_doctype_is_absent(self):
        db = _FakeDB({})
        db.exists = lambda *a, **k: False
        returned, _ = self._execute(db)
        self.assertIsNone(returned)
        self.assertEqual(db.ddl, [])
        self.assertEqual(db.commits, 0)


if __name__ == "__main__":
    unittest.main()
