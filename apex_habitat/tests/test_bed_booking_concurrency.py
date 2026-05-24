"""Regression test: bed booking concurrency protection (#42).

File-level test — no Frappe site needed. Uses ast and stdlib only.

This test verifies that the SELECT ... FOR UPDATE pattern is present in the
Accommodation Assignment on_submit handler, providing row-level lock
protection against concurrent double-booking.

What a full stress test would do
---------------------------------
A proper concurrency stress test would:

1. Provision a real Frappe site with a single available bed.
2. Spawn 10,000 concurrent threads (or async coroutines), each attempting to
   submit an Accommodation Assignment for the same bed simultaneously.
3. Assert that exactly ONE assignment succeeds (docstatus=1, bed status="Occupied")
   and all 9,999 others raise a ValidationError ("Bed was just taken by another
   assignment").
4. Verify that the Accommodation Bed record shows status="Occupied" and that
   current_occupancy on the room equals 1.
5. Measure P99 latency under contention to confirm the lock does not cause
   unacceptable serialisation delay at the expected operational concurrency
   (typically 2-5 simultaneous check-ins at a single site).

Why this requires a real bench environment
------------------------------------------
- The SELECT ... FOR UPDATE statement is only meaningful inside a MySQL/MariaDB
  InnoDB transaction, which Frappe wraps around each document submit.
- Python threading alone cannot reproduce database-level row locking; the lock
  is acquired by the DB engine, not by Python.
- A mock or in-memory SQLite database does not support FOR UPDATE semantics.
- The test therefore validates code presence (the guard is in the source) and
  relies on the DBA/ops team to run the live stress test before each major
  release on a staging bench with the production DB engine.
"""

import ast
import os
import unittest

ASSIGNMENT_CONTROLLER = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "habitat",
        "doctype",
        "accommodation_assignment",
        "accommodation_assignment.py",
    )
)

# The exact SQL fragment that must appear in the on_submit path.
FOR_UPDATE_FRAGMENT = "FOR UPDATE"


class TestBedBookingConcurrencyGuard(unittest.TestCase):
    """Verify that the SELECT FOR UPDATE lock guard exists in the source."""

    def _load_source(self):
        self.assertTrue(
            os.path.exists(ASSIGNMENT_CONTROLLER),
            f"Controller not found: {ASSIGNMENT_CONTROLLER}",
        )
        with open(ASSIGNMENT_CONTROLLER, encoding="utf-8") as fh:
            return fh.read()

    def test_for_update_sql_present(self):
        """The controller source must contain a SELECT ... FOR UPDATE statement.

        This is the InnoDB row-level lock that prevents two concurrent
        on_submit calls from both reading the bed as 'Available' and both
        proceeding to mark it 'Occupied'.
        """
        source = self._load_source()
        self.assertIn(
            FOR_UPDATE_FRAGMENT,
            source,
            "The string 'FOR UPDATE' was not found in accommodation_assignment.py. "
            "The SELECT FOR UPDATE concurrency guard has been removed. "
            "Restore it in the on_submit handler before merging.",
        )

    def test_for_update_is_in_on_submit(self):
        """The FOR UPDATE SQL must be called within the on_submit function body.

        This ensures the lock is acquired at submit time (the critical
        window), not only in a utility helper that might not be called.
        """
        source = self._load_source()
        tree = ast.parse(source, filename=ASSIGNMENT_CONTROLLER)

        on_submit_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "on_submit":
                on_submit_node = node
                break

        self.assertIsNotNone(
            on_submit_node,
            "Function 'on_submit' not found in accommodation_assignment.py. "
            "The submit hook has been renamed or removed.",
        )

        # Extract source lines that belong to on_submit
        source_lines = source.splitlines()
        start = on_submit_node.lineno - 1
        end = on_submit_node.end_lineno
        func_source = "\n".join(source_lines[start:end])

        self.assertIn(
            FOR_UPDATE_FRAGMENT,
            func_source,
            "The 'FOR UPDATE' lock was not found inside the on_submit function body. "
            "It may have been moved out of the critical section. "
            "The lock must be acquired before checking bed status in on_submit.",
        )

    def test_on_submit_checks_bed_status_after_lock(self):
        """After acquiring the lock, on_submit must re-read bed status.

        Reading the status before the lock is pointless — another transaction
        could change the status between the read and the lock acquisition.
        The pattern 'FOR UPDATE ... get_value ... status' must appear in
        that order within on_submit.
        """
        source = self._load_source()
        tree = ast.parse(source, filename=ASSIGNMENT_CONTROLLER)

        on_submit_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "on_submit":
                on_submit_node = node
                break

        self.assertIsNotNone(on_submit_node, "on_submit not found")

        source_lines = source.splitlines()
        start = on_submit_node.lineno - 1
        end = on_submit_node.end_lineno
        func_source = "\n".join(source_lines[start:end])

        lock_pos = func_source.find(FOR_UPDATE_FRAGMENT)
        status_check_pos = func_source.find("get_value")

        self.assertGreater(
            lock_pos,
            -1,
            "FOR UPDATE not found in on_submit (checked again for position).",
        )
        self.assertGreater(
            status_check_pos,
            -1,
            "get_value (status re-read) not found in on_submit after lock.",
        )
        self.assertGreater(
            status_check_pos,
            lock_pos,
            "get_value (status re-read) appears BEFORE the FOR UPDATE lock. "
            "The status must be read AFTER acquiring the lock to be race-free.",
        )


if __name__ == "__main__":
    unittest.main()
