# Copyright (c) 2026, AFMCO and contributors
"""Integration test: the purge, run against a real ``tabAccess Log``.

``test_access_log_cleanup.py`` proves the ALGORITHM against an in-memory double.
Two mitigations narrow the gap - the double reads its strictness from
``SCAN_SQL``, and a separate test pins the measured columns to
``PAYLOAD_FIELDS`` - but a double can never prove that the SQL text parses, that
``OCTET_LENGTH`` measures what Python's ``len(...encode())`` measured, or that
``frappe.db.delete`` removes the rows the scan named. This module executes the
real statements against real rows and asserts the three outcomes the card names:
the oversized row is gone, the normal row survives, the exact-boundary row is
preserved.

Isolation. Every row this module creates carries a per-test random marker in
``reference_document`` - a Data column that is NOT one of ``PAYLOAD_FIELDS``, so
it cannot perturb the size predicate under test. The threshold is DERIVED from
the boundary row's measured size rather than assumed, so any storage-layer
transformation of the payload is absorbed instead of making the boundary
approximate. Rows the test did not create are never asserted away: the purge
legitimately deletes any pre-existing oversized row, so those are counted before
the run and reconciled after it, and the assertion that nothing at or below the
threshold was touched is what proves no collateral damage. Nothing commits, so
``FrappeTestCase``'s rollback undoes the whole thing.

Two facts already on record are pinned here as executed observations rather than
comments: ``OCTET_LENGTH`` in the WHERE clause is not sargable, so every run
costs a full table scan (test_scan_plan_is_a_full_table_scan records the plan and
the row count it was measured at), and ``SCAN_SQL`` is MariaDB-quoted, so the
suite is explicitly skipped rather than silently green on Postgres.
"""

from __future__ import annotations

import time
import unittest
from contextlib import contextmanager

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils import access_log_cleanup as mod

# Payload sizes in bytes. The boundary row defines the threshold, so "exactly on
# the threshold" is exact by construction rather than by assumption.
SMALL_BYTES = 128
BOUNDARY_BYTES = 8192
OVER_BY_ONE_BYTES = BOUNDARY_BYTES + 1
BIG_BYTES = BOUNDARY_BYTES * 8

# Generous enough that one run clears every candidate in a single pass.
BATCH_SIZE = 500
MAX_BATCHES = 20


@contextmanager
def _site_config(**overrides):
    """Apply purge knobs to the live site config and restore them afterwards."""
    previous = {key: frappe.conf.get(key) for key in overrides}
    frappe.conf.update(overrides)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                frappe.conf.pop(key, None)
            else:
                frappe.conf[key] = value


class TestAccessLogPurgeAgainstRealTable(FrappeTestCase):
    def setUp(self):
        # Checked here, not as a class decorator: a decorator is evaluated at
        # import time, when frappe.db may not be bound yet, which would skip the
        # whole class into a false green.
        if frappe.db.db_type != "mariadb":
            self.skipTest("SCAN_SQL quotes identifiers with backticks, so it is MariaDB-only")
        frappe.set_user("Administrator")
        self.marker = frappe.generate_hash(length=16)
        self.small = self._seed(SMALL_BYTES)
        self.boundary = self._seed(BOUNDARY_BYTES)
        self.over_by_one = self._seed(OVER_BY_ONE_BYTES)
        self.big = self._seed(BIG_BYTES)

    def tearDown(self):
        # Explicit cleanup so the module is re-runnable even outside a rolled-back
        # transaction. Only rows carrying this test's marker are touched.
        frappe.db.delete(mod.DOCTYPE, {"reference_document": self.marker})

    def _seed(self, payload_bytes: int) -> str:
        """Insert one real Access Log row whose payload is ASCII of a known length."""
        return (
            frappe.get_doc(
                {
                    "doctype": mod.DOCTYPE,
                    "user": "Administrator",
                    "export_from": "Apex access log purge integration",
                    "reference_document": self.marker,
                    "page": "x" * payload_bytes,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _measured_sizes(self) -> dict[str, int]:
        """Real payload_bytes per seeded row, using the module's own expression."""
        rows = frappe.db.sql(
            f"SELECT `name`, {mod._PAYLOAD_BYTES} AS payload_bytes "
            "FROM `tabAccess Log` WHERE `reference_document` = %(marker)s",
            {"marker": self.marker},
            as_dict=True,
        )
        return {row["name"]: int(row["payload_bytes"]) for row in rows}

    def _count_at_or_below(self, threshold: int) -> int:
        return frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabAccess Log` WHERE {mod._PAYLOAD_BYTES} <= %(threshold)s",
            {"threshold": threshold},
        )[0][0]

    def _names_above(self, threshold: int) -> set[str]:
        rows = frappe.db.sql(
            f"SELECT `name` FROM `tabAccess Log` WHERE {mod._PAYLOAD_BYTES} > %(threshold)s",
            {"threshold": threshold},
        )
        return {row[0] for row in rows}

    def _threshold(self) -> tuple[int, dict[str, int]]:
        sizes = self._measured_sizes()
        self.assertEqual(len(sizes), 4, "the four seeded rows must all be present")
        return sizes[self.boundary], sizes

    def test_seeded_payloads_measure_in_the_database_exactly_as_written(self):
        """Sentinel: if storage transformed the payload, every size below is a lie."""
        threshold, sizes = self._threshold()
        self.assertEqual(threshold, BOUNDARY_BYTES)
        self.assertEqual(sizes[self.small], SMALL_BYTES)
        self.assertEqual(sizes[self.over_by_one], BOUNDARY_BYTES + 1)
        self.assertEqual(sizes[self.big], BIG_BYTES)

    def test_real_scan_and_delete_removes_only_rows_above_the_threshold(self):
        threshold, sizes = self._threshold()
        self.assertGreater(sizes[self.big], threshold)
        self.assertLess(sizes[self.small], threshold)

        below_before = self._count_at_or_below(threshold)
        expected_deletions = self._names_above(threshold)
        self.assertIn(self.big, expected_deletions)
        self.assertIn(self.over_by_one, expected_deletions)
        self.assertNotIn(self.boundary, expected_deletions)

        with _site_config(
            apex_access_log_max_payload_bytes=threshold,
            apex_access_log_purge_batch_size=BATCH_SIZE,
            apex_access_log_purge_max_batches=MAX_BATCHES,
        ):
            result = mod.purge_oversized_access_logs()

        self.assertFalse(result["truncated"], "the run must not be budget-bound here")
        self.assertEqual(
            result["deleted"],
            len(expected_deletions),
            "the delete must remove exactly the rows the scan identified",
        )
        self.assertFalse(
            frappe.db.exists(mod.DOCTYPE, self.big), "the oversized row must be gone"
        )
        self.assertFalse(
            frappe.db.exists(mod.DOCTYPE, self.over_by_one),
            "one byte over the threshold must still be purged",
        )
        self.assertTrue(
            frappe.db.exists(mod.DOCTYPE, self.boundary),
            "the row exactly on the threshold must be preserved - the comparison is strict",
        )
        self.assertTrue(
            frappe.db.exists(mod.DOCTYPE, self.small), "the normal row must survive"
        )
        self.assertEqual(
            self._count_at_or_below(threshold),
            below_before,
            "no row at or below the threshold may be deleted, including rows this "
            "test did not create",
        )

    def test_dry_run_reports_the_oversized_rows_without_deleting_or_leaking_them(self):
        threshold, _ = self._threshold()
        with _site_config(
            apex_access_log_max_payload_bytes=threshold,
            apex_access_log_purge_batch_size=BATCH_SIZE,
        ):
            result = mod.purge_oversized_access_logs(dry_run=True)

        reported = {record["name"] for record in result["records"]}
        self.assertIn(self.big, reported)
        self.assertIn(self.over_by_one, reported)
        self.assertNotIn(self.boundary, reported)
        self.assertNotIn(self.small, reported)
        self.assertTrue(frappe.db.exists(mod.DOCTYPE, self.big), "a dry run must not delete")
        self.assertNotIn(
            "x" * 64,
            repr(result),
            "the real scan must return sizes only - no payload body may reach the caller",
        )
        for record in result["records"]:
            self.assertEqual(tuple(record), mod.AUDIT_FIELDS)

    def test_rerunning_the_purge_finds_nothing_left(self):
        threshold, _ = self._threshold()
        knobs = {
            "apex_access_log_max_payload_bytes": threshold,
            "apex_access_log_purge_batch_size": BATCH_SIZE,
            "apex_access_log_purge_max_batches": MAX_BATCHES,
        }
        with _site_config(**knobs):
            first = mod.purge_oversized_access_logs()
            second = mod.purge_oversized_access_logs()

        self.assertGreaterEqual(first["deleted"], 2)
        self.assertEqual(second["deleted"], 0, "a second run must be a no-op")
        self.assertEqual(second["batches"], 0)
        self.assertTrue(frappe.db.exists(mod.DOCTYPE, self.boundary))

    def test_scan_plan_is_a_full_table_scan_and_the_cost_is_recorded(self):
        """Record the real plan and timing so the full-scan cost is a number.

        ``OCTET_LENGTH(col)`` in the WHERE clause is not sargable: no index can
        satisfy it, so the optimiser must read every row. This asserts that is
        still what the database does and prints the row count it was measured at.
        """
        threshold, _ = self._threshold()
        params = {"threshold": threshold, "limit": BATCH_SIZE * MAX_BATCHES + 1}

        plan = frappe.db.sql("EXPLAIN " + mod.SCAN_SQL, params, as_dict=True)
        self.assertTrue(plan, "EXPLAIN returned no rows")
        step = plan[0]

        started = time.perf_counter()
        frappe.db.sql(mod.SCAN_SQL, params, as_dict=True)
        elapsed_ms = (time.perf_counter() - started) * 1000
        total_rows = frappe.db.count(mod.DOCTYPE)

        print(
            f"\n[access-log] scan cost: rows_in_table={total_rows} "
            f"plan_type={step.get('type')} key={step.get('key')} "
            f"rows_examined={step.get('rows')} extra={step.get('Extra')!r} "
            f"scan_ms={elapsed_ms:.1f}"
        )

        self.assertIsNone(
            step.get("key"),
            "the scan now uses an index. Making the predicate sargable is an "
            "improvement, but the recorded full-scan cost above is then stale - "
            f"update this test with the new plan: {step}",
        )
        self.assertEqual(
            step.get("type"),
            "ALL",
            f"expected a full table scan for a non-sargable OCTET_LENGTH filter: {step}",
        )


if __name__ == "__main__":
    unittest.main()
