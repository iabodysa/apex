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

Two layers, because the named lists below cover seven functions and the app ships 23
bare rollbacks: the lists pin the specific helpers whose fix must not regress, and a
whole-tree sweep grades every other file for the shape that actually costs a run — a
bare rollback in a handler that then lets its loop reach the next row.

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

from apex.tests.source_tree import APP_ROOT, parse, production_py_files, rel

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


# The lists above name seven functions, and that is the whole reason this guard could
# stay green while the clause it exists to defend went unproven: 23 bare
# frappe.db.rollback() calls ship in apex/, so a hand-kept list said nothing about the
# other sixteen. The sweep below reads the tree instead, and grades the shape that
# actually hurts — a rollback that ends the transaction and then lets the loop reach
# the next row.

# frappe.throw() raises, but the AST sees only a call.
_EXIT_CALLS = {"throw", "raise_exception"}


def _is_bare_rollback(call):
    if getattr(call.func, "attr", None) != "rollback":
        return False
    if getattr(getattr(call.func, "value", None), "attr", None) != "db":
        return False
    return not any(kw.arg == "save_point" for kw in call.keywords)


def _handler_leaves_the_loop(handler):
    """Does this handler stop the loop from reaching the next row?

    Only the handler's OWN statements count. A ``raise`` nested inside an ``if`` still
    leaves a path that falls through to the next iteration — the dangerous shape — so a
    conditional exit deliberately does not clear the handler.
    """
    for node in handler.body:
        if isinstance(node, (ast.Return, ast.Raise, ast.Break)):
            return True
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "attr", None) in _EXIT_CALLS
        ):
            return True
    return False


def _commits(try_node):
    """A guarded body that commits bounds its own rollback: everything earlier is
    already durable, so the rollback can only undo this iteration. workflow_utils.py
    :65,79 are the app's commit-bounded pair, correct as written."""
    return any(
        isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "commit"
        for stmt in try_node.body
        for node in ast.walk(stmt)
    )


def _loops_that_resume_after_a_bare_rollback(tree):
    """Line numbers of every bare rollback whose handler lets an enclosing loop go on.

    Written as a descent rather than an ``ast.walk`` because the verdict depends on
    ANCESTRY: the same call is safe outside a loop and a run-destroyer inside one.
    """
    found = []

    def visit(node, in_loop):
        # Dispatch on the node itself, not on its children: a Try handed in directly
        # as a loop-body statement would otherwise never reach visit_try.
        if isinstance(node, ast.Try):
            visit_try(node, in_loop)
            return
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            for stmt in node.body + node.orelse:
                visit(stmt, True)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for stmt in node.body:  # a nested def does not run in the caller's loop
                visit(stmt, False)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, in_loop)

    def visit_try(try_node, in_loop):
        for stmt in try_node.body + try_node.orelse + try_node.finalbody:
            visit(stmt, in_loop)
        bounded = _commits(try_node)
        for handler in try_node.handlers:
            if in_loop and not bounded and not _handler_leaves_the_loop(handler):
                found.extend(
                    call.lineno
                    for call in ast.walk(handler)
                    if isinstance(call, ast.Call) and _is_bare_rollback(call)
                )
            for stmt in handler.body:
                visit(stmt, in_loop)

    visit(tree, False)
    return sorted(found)


# Every shape the sweep must tell apart. Only one of them is the defect.
CONTROL_SWEEP = """
import frappe


def resumes():
    for row in rows:
        try:
            frappe.get_doc(row).insert()
        except Exception:
            frappe.db.rollback()
            frappe.log_error("kept going")


def leaves_the_loop():
    for row in rows:
        try:
            frappe.get_doc(row).insert()
        except Exception:
            frappe.db.rollback()
            raise


def commit_bounded():
    for row in rows:
        try:
            frappe.get_doc(row).insert()
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()


def outside_any_loop():
    try:
        frappe.get_doc({}).insert()
    except Exception:
        frappe.db.rollback()


def scoped():
    for row in rows:
        frappe.db.savepoint("s")
        try:
            frappe.get_doc(row).insert()
        except Exception:
            frappe.db.rollback(save_point="s")
"""


class TestTheSweepTellsTheFourShapesApart(unittest.TestCase):
    """A sweep that flags nothing is indistinguishable from a sweep that is broken."""

    def _hits(self, source):
        lines = source.splitlines()
        return [
            lines[n - 1].strip()
            for n in _loops_that_resume_after_a_bare_rollback(ast.parse(source))
        ]

    def test_it_flags_only_the_loop_that_resumes(self):
        self.assertEqual(self._hits(CONTROL_SWEEP), ["frappe.db.rollback()"])

    def test_a_conditional_raise_does_not_clear_the_handler(self):
        source = (
            "import frappe\n"
            "def f():\n"
            "    for row in rows:\n"
            "        try:\n"
            "            go(row)\n"
            "        except Exception:\n"
            "            frappe.db.rollback()\n"
            "            if fatal:\n"
            "                raise\n"
        )
        self.assertEqual(self._hits(source), ["frappe.db.rollback()"])


class TestNoLoopResumesAfterAWholeTransactionRollback(unittest.TestCase):
    def test_no_shipped_loop_continues_past_a_bare_rollback(self):
        offenders = []
        for path in production_py_files():
            tree = parse(path)
            if tree is None:
                continue
            offenders += [
                f"{rel(path)}:{line}"
                for line in _loops_that_resume_after_a_bare_rollback(tree)
            ]
        self.assertEqual(
            offenders,
            [],
            "frappe.db.rollback() with no save_point ends the whole transaction "
            "(frappe/database/database.py:1186-1201), so a loop that reaches the next "
            "row after one has already thrown away every row the run wrote — and the "
            "released savepoint makes the caller's next rollback(save_point=...) raise "
            "MariaDB 1305. Take a savepoint per row and roll back to that. "
            f"Offenders: {offenders}",
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
