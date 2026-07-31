# Copyright (c) 2026, AFMCO and contributors
"""Every shared recovery path must scope its rollback, or take none at all.

``frappe.db.rollback()`` with no ``save_point`` is not a local undo: it ends the
whole transaction (frappe/database/database.py:1186-1201). Inside a loop that was
taught to survive one bad row it therefore discards every row the run already
wrote, and it releases the caller's savepoint, so a later
``rollback(save_point=...)`` in the same iteration raises MariaDB 1305 uncaught.

Two shapes are correct, and which one applies is decided by whether the guarded
block commits:

  * a row loop takes its OWN savepoint and rolls back to it;
  * a block that runs DDL takes NEITHER, because MariaDB implicitly commits around
    ALTER TABLE and ``frappe.db.add_unique`` commits explicitly first
    (frappe/database/mariadb/database.py:442-451). Verified on a live MariaDB: with
    a savepoint open, both a succeeding and a failing ``ALTER TABLE`` leave
    ``rollback(save_point=...)`` raising ``(1305, 'SAVEPOINT ... does not exist')``.
    A savepoint there would abort the very migrate the helper exists to survive.

This is a static guard because the failure is a migrate-time transaction effect
that no per-row test reproduces cheaply. The matching BEHAVIOUR proof lives beside
the helper it protects, in test_operations_alert_helper.py.

Colocated here rather than in apex/tests/: the two helpers it guards most closely
(operations_alert, ledger_index) are this package's, and the central directory
only shrinks (tests/test_colocation_ratchet.py).

Frappe-free by construction — it reads the shipped tree, so it runs without a site:

    python3 -m unittest apex.apex_core.utils.test_rollback_savepoint_scope
"""

from __future__ import annotations

import ast
import os
import unittest

from apex.tests.source_tree import APP_ROOT, parse, rel

# Functions that recover row-by-row and must roll back only their own row.
SCOPED = [
    ("apex_core/utils/operations_alert.py", "insert_operations_alert"),
    ("salis/utils/__init__.py", "raise_rider_clearance_task"),
    ("patches/v1_0/seed_salis_roles.py", "execute"),
    ("patches/v1_0/seed_salis_authority_roles.py", "execute"),
    ("patches/v1_x/migrate_scheduled_task_template_to_assignments.py", "execute"),
]

# Functions whose guarded block runs DDL, where any rollback is wrong.
DDL_FREE = [
    ("apex_core/utils/ledger_index.py", "add_index_guarded"),
    ("apex_core/utils/ledger_index.py", "add_unique_guarded"),
]

# A bare rollback and a scoped one, so the detector is shown to tell them apart
# rather than being trusted to.
CONTROL = """
import frappe


def bare():
    try:
        frappe.get_doc({}).insert()
    except Exception:
        frappe.db.rollback()


def scoped():
    frappe.db.savepoint("x")
    try:
        frappe.get_doc({}).insert()
    except Exception:
        frappe.db.rollback(save_point="x")
"""


def _rollbacks(tree, name):
    """``(lineno, has_save_point)`` for every ``frappe.db.rollback`` call inside the
    function ``name``.

    Scoped to the one function: these modules hold several recovery paths and a
    whole-file scan could not say which of them was fixed.
    """
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != name:
            continue
        found = []
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            if getattr(call.func, "attr", None) != "rollback":
                continue
            found.append(
                (call.lineno, any(kw.arg == "save_point" for kw in call.keywords))
            )
        return found
    raise AssertionError(f"{name} is gone from the module — the guard reads a stale name")


def _tree(relpath):
    path = os.path.join(APP_ROOT, relpath)
    tree = parse(path)
    assert tree is not None, f"{rel(path)} did not parse"
    return tree


class TestTheDetectorSeesBothShapes(unittest.TestCase):
    """"No bare rollback found" is what a broken detector reports too."""

    def setUp(self):
        self.tree = ast.parse(CONTROL)

    def test_it_flags_a_bare_rollback(self):
        self.assertEqual(_rollbacks(self.tree, "bare"), [(9, False)])

    def test_it_accepts_a_scoped_rollback(self):
        self.assertEqual(_rollbacks(self.tree, "scoped"), [(17, True)])


class TestRowLoopsRollBackOnlyTheirOwnRow(unittest.TestCase):
    def test_every_shared_recovery_path_passes_a_save_point(self):
        offenders = []
        for relpath, func in SCOPED:
            calls = _rollbacks(_tree(relpath), func)
            self.assertTrue(
                calls,
                f"{relpath} -> {func} no longer rolls back at all — if that is "
                "deliberate, move it to DDL_FREE with the reason",
            )
            offenders += [
                f"{relpath}:{line} ({func})" for line, scoped in calls if not scoped
            ]
        self.assertEqual(
            offenders,
            [],
            "a bare frappe.db.rollback() here ends the whole transaction: it discards "
            "every row the calling loop already wrote and releases the caller's "
            "savepoint, so the next rollback(save_point=...) raises MariaDB 1305. "
            f"Take a savepoint per row and roll back to it. Offenders: {offenders}",
        )


class TestDdlBlocksTakeNoRollbackAtAll(unittest.TestCase):
    """A savepoint cannot survive the DDL it would be protecting."""

    def test_the_index_helpers_do_not_roll_back(self):
        offenders = []
        for relpath, func in DDL_FREE:
            offenders += [
                f"{relpath}:{line} ({func})" for line, _scoped in _rollbacks(_tree(relpath), func)
            ]
        self.assertEqual(
            offenders,
            [],
            "MariaDB implicitly commits around ALTER TABLE and frappe.db.add_unique "
            "commits before its own, so by the time this except runs the caller's work "
            "is committed and its savepoints are released. A bare rollback undoes "
            "nothing while resetting the caller's commit hooks; a scoped one raises "
            f"1305 uncaught and aborts migrate. Offenders: {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
