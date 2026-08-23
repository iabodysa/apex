# Copyright (c) 2026, afmcoltd

"""The boarding idempotency predicate four entry points share.

The Masar confirm, the manual desk and the boarding flow all ask whether this worker
already boarded this trip. A second copy of the answer makes a re-confirm stop being
idempotent and double-counts the headcount, so the one property that matters is that
every caller reads the same rule off the same log object.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api.boarding import already_boarded


def _log(*events):
    """A boarding log shaped as the callers hold it — the predicate fetches nothing."""
    return frappe._dict(
        boarding_events=[
            frappe._dict(worker=worker, is_unregistered=unregistered)
            for worker, unregistered in events
        ]
    )


class TestAlreadyBoarded(FrappeTestCase):
    """Pure predicate over a log the caller already holds."""

    def test_a_registered_row_counts(self):
        self.assertTrue(already_boarded(_log(("W1", 0)), "W1"))

    def test_an_unregistered_row_never_counts(self):
        """It records that someone boarded without a worker record, so it can neither
        be matched to this worker nor block their own boarding."""
        self.assertFalse(already_boarded(_log(("W1", 1)), "W1"))

    def test_a_different_worker_does_not_count(self):
        self.assertFalse(already_boarded(_log(("W1", 0)), "W2"))

    def test_an_empty_log_is_not_boarded(self):
        self.assertFalse(already_boarded(_log(), "W1"))
        self.assertFalse(already_boarded(frappe._dict(boarding_events=None), "W1"))

    def test_one_registered_row_among_others_is_enough(self):
        self.assertTrue(already_boarded(_log(("W2", 0), ("W1", 1), ("W1", 0)), "W1"))

    def test_only_one_definition_of_this_predicate_exists(self):
        """A second copy anywhere is the defect, so the tree is asked directly.

        ``boarding_flow`` and ``manual_boarding`` both reach it through function-local
        imports, so identity is proved on the definitions in the tree rather than on
        every module's attributes.
        """
        import ast
        import pathlib

        from apex.salis.api import boarding, masar

        self.assertIs(masar.already_boarded, boarding.already_boarded)

        root = pathlib.Path(boarding.__file__).parents[3]
        definitions = [
            f"{path}:{node.lineno}"
            for path in root.rglob("*.py")
            for node in ast.walk(ast.parse(path.read_text()))
            if isinstance(node, ast.FunctionDef) and node.name.endswith("already_boarded")
        ]
        self.assertEqual(len(definitions), 1, definitions)
