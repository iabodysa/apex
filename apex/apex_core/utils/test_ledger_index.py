# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for apex_core.utils.ledger_index guarded-index helpers.

The DDL is mocked (no live DB) so the idempotency and failure-handling branches
of ``add_index_guarded`` / ``add_unique_guarded`` are exercised directly: a
pre-existing index/constraint is a no-op, a clean add returns True, and a DDL
error rolls back and returns False instead of aborting migrate.
"""

from __future__ import annotations

import unittest
from unittest import mock

from apex.apex_core.utils import ledger_index


class TestAddIndexGuarded(unittest.TestCase):
    def test_noop_when_index_already_exists(self):
        with mock.patch.object(ledger_index, "_index_exists", return_value=True), \
             mock.patch.object(ledger_index, "frappe") as mf:
            self.assertTrue(ledger_index.add_index_guarded("Foo", ["a", "b"], "idx_foo"))
            mf.db.sql.assert_not_called()

    def test_creates_index_when_absent(self):
        with mock.patch.object(ledger_index, "_index_exists", side_effect=[False, True]), \
             mock.patch.object(ledger_index, "frappe") as mf:
            self.assertTrue(ledger_index.add_index_guarded("Foo", ["a", "b"], "idx_foo"))
            mf.db.sql.assert_called_once()
            sql = mf.db.sql.call_args[0][0]
            self.assertIn("ADD INDEX `idx_foo`", sql)
            self.assertIn("`a`, `b`", sql)

    def test_returns_false_and_rolls_nothing_back_on_ddl_error(self):
        with mock.patch.object(ledger_index, "_index_exists", return_value=False), \
             mock.patch.object(ledger_index, "frappe") as mf:
            mf.db.sql.side_effect = Exception("boom")
            self.assertFalse(ledger_index.add_index_guarded("Foo", ["a"], "idx_foo"))
            # MariaDB implicitly commits around ALTER TABLE even when it fails, so the
            # caller's work is committed and its savepoints released before this runs:
            # a bare rollback undoes nothing while resetting the caller's commit hooks,
            # and a scoped one raises 1305 and aborts the migrate.
            mf.db.rollback.assert_not_called()
            mf.log_error.assert_called_once()


class TestAddUniqueGuarded(unittest.TestCase):
    def test_noop_when_constraint_already_exists(self):
        with mock.patch.object(ledger_index, "_constraint_exists", return_value=True), \
             mock.patch.object(ledger_index, "frappe") as mf:
            self.assertTrue(ledger_index.add_unique_guarded("Foo", ["a"], "uq_foo"))
            mf.db.add_unique.assert_not_called()

    def test_creates_constraint_when_absent(self):
        with mock.patch.object(ledger_index, "_constraint_exists", side_effect=[False, True]), \
             mock.patch.object(ledger_index, "frappe") as mf:
            self.assertTrue(ledger_index.add_unique_guarded("Foo", ["a", "b"], "uq_foo"))
            mf.db.add_unique.assert_called_once_with("Foo", ["a", "b"], constraint_name="uq_foo")

    def test_returns_false_and_logs_blockers_on_duplicate_data(self):
        with mock.patch.object(ledger_index, "_constraint_exists", return_value=False), \
             mock.patch.object(ledger_index, "_log_blocking_duplicates") as log_dupes, \
             mock.patch.object(ledger_index, "frappe") as mf:
            mf.db.add_unique.side_effect = Exception("1062 duplicate")
            self.assertFalse(ledger_index.add_unique_guarded("Foo", ["a"], "uq_foo"))
            # frappe.db.add_unique commits before its own ALTER TABLE
            # (frappe/database/mariadb/database.py:447), so there is nothing left to
            # roll back and no savepoint left to roll back to.
            mf.db.rollback.assert_not_called()
            log_dupes.assert_called_once_with("Foo", ["a"], "uq_foo")


if __name__ == "__main__":
    unittest.main()
