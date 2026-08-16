# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for apex_core.utils.access_log_cleanup.

The database is replaced by an in-memory double that holds real payload strings
and evaluates the same rule the scan query encodes: the sum of the three payload
columns, strictly above the threshold, biggest first, bounded by LIMIT. That
exercises the purge algorithm - boundary, per-field detection, batching,
idempotent reruns, rollback - with no live site and no self-skip.

A double cannot vouch for the SQL text, so the query is asserted separately: it
must measure the payload columns with OCTET_LENGTH instead of selecting their
bodies, and it must compare strictly. An end-to-end check against a real MariaDB
table is still worth having; these tests do not replace it.
"""

from __future__ import annotations

import ast
import inspect
import re
import unittest
from unittest import mock

import apex.hooks
from apex.apex_core.utils import access_log_cleanup as mod

JOB_PATH = "apex.apex_core.utils.access_log_cleanup.purge_oversized_access_logs"


class _FakeDB:
    """Minimal stand-in for frappe.db holding Access Log rows as real strings."""

    def __init__(self, rows: dict):
        self.rows = {name: dict(payload) for name, payload in rows.items()}
        self._committed = {name: dict(payload) for name, payload in rows.items()}
        self.deleted_batches: list[list[str]] = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_on_batch: int | None = None

    def commit(self):
        self.commits += 1
        self._committed = {name: dict(payload) for name, payload in self.rows.items()}

    def rollback(self):
        # Models the real transaction: with no commit in the run, rolling back
        # restores every row the run had deleted.
        self.rollbacks += 1
        self.rows = {name: dict(payload) for name, payload in self._committed.items()}

    def _measure(self, name: str) -> dict:
        row = self.rows[name]
        sizes = {
            f"{field}_bytes": len((row.get(field) or "").encode("utf-8"))
            for field in mod.PAYLOAD_FIELDS
        }
        sizes["payload_bytes"] = sum(sizes.values())
        sizes["name"] = name
        # A real scan never returns bodies; this double deliberately does, so the
        # module's own sanitisation is what has to strip them.
        sizes.update(row)
        return sizes

    def sql(self, query, params=None, as_dict=False):
        assert query is mod.SCAN_SQL, "unexpected query issued"
        assert as_dict is True, "scan must read rows as dicts"
        threshold = params["threshold"]
        limit = params["limit"]
        # Honour the predicate the real query actually encodes, so relaxing the
        # comparison in SCAN_SQL breaks the boundary tests rather than sliding by.
        strict = ">= %(threshold)s" not in query
        matches = [self._measure(name) for name in self.rows]
        matches = [
            row
            for row in matches
            if (row["payload_bytes"] > threshold if strict else row["payload_bytes"] >= threshold)
        ]
        matches.sort(key=lambda row: (-row["payload_bytes"], row["name"]))
        return matches[:limit]

    def delete(self, doctype, filters):
        assert doctype == mod.DOCTYPE
        operator, names = filters["name"]
        assert operator == "in"
        if self.fail_on_batch is not None and len(self.deleted_batches) == self.fail_on_batch:
            raise RuntimeError("database went away")
        self.deleted_batches.append(list(names))
        for name in names:
            del self.rows[name]


def _payload(size: int, marker: str = "x") -> str:
    return marker * size


def _run(fake: _FakeDB, conf: dict | None = None, **kwargs):
    """Invoke the job with frappe replaced, returning (result, frappe_mock)."""
    with mock.patch.object(mod, "frappe") as frappe_mock:
        frappe_mock.db = fake
        frappe_mock.conf = conf or {}
        result = mod.purge_oversized_access_logs(**kwargs)
    return result, frappe_mock


class TestThresholdBoundary(unittest.TestCase):
    def test_below_threshold_rows_are_preserved(self):
        fake = _FakeDB({"AL-small": {"page": _payload(50)}})
        result, _ = _run(fake, {"apex_access_log_max_payload_bytes": 100})
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(fake.deleted_batches, [])
        self.assertIn("AL-small", fake.rows)

    def test_row_exactly_on_threshold_is_preserved_and_one_byte_over_is_purged(self):
        fake = _FakeDB(
            {
                "AL-exact": {"page": _payload(100)},
                "AL-over": {"page": _payload(101)},
            }
        )
        result, _ = _run(fake, {"apex_access_log_max_payload_bytes": 100})
        self.assertEqual(result["deleted"], 1)
        self.assertIn("AL-exact", fake.rows, "a row exactly on the threshold must survive")
        self.assertNotIn("AL-over", fake.rows)

    def test_oversize_is_detected_in_page_columns_and_filters_alike(self):
        fake = _FakeDB(
            {
                "AL-page": {"page": _payload(120)},
                "AL-columns": {"columns": _payload(120)},
                "AL-filters": {"filters": _payload(120)},
                "AL-combined": {"page": _payload(40), "columns": _payload(40), "filters": _payload(40)},
                "AL-normal": {"page": _payload(10), "filters": _payload(10)},
            }
        )
        result, _ = _run(fake, {"apex_access_log_max_payload_bytes": 100})
        self.assertEqual(result["deleted"], 4)
        self.assertEqual(list(fake.rows), ["AL-normal"])


class TestBatching(unittest.TestCase):
    def _oversized(self, count: int) -> dict:
        return {f"AL-{index:02d}": {"page": _payload(200)} for index in range(count)}

    def test_deletion_is_split_into_bounded_batches(self):
        fake = _FakeDB(self._oversized(5))
        result, _ = _run(
            fake,
            {"apex_access_log_max_payload_bytes": 100, "apex_access_log_purge_batch_size": 2},
        )
        self.assertEqual([len(batch) for batch in fake.deleted_batches], [2, 2, 1])
        self.assertEqual(result["batches"], 3)
        self.assertEqual(result["deleted"], 5)
        self.assertFalse(result["truncated"])
        self.assertEqual(fake.rows, {})

    def test_max_batches_bounds_one_run_and_reports_truncation(self):
        fake = _FakeDB(self._oversized(6))
        result, _ = _run(
            fake,
            {
                "apex_access_log_max_payload_bytes": 100,
                "apex_access_log_purge_batch_size": 2,
                "apex_access_log_purge_max_batches": 2,
            },
        )
        self.assertEqual(result["deleted"], 4)
        self.assertEqual(result["batches"], 2)
        self.assertTrue(result["truncated"], "leftover oversized rows must be reported")
        self.assertEqual(len(fake.rows), 2)

    def test_rerun_after_a_full_purge_is_a_no_op(self):
        fake = _FakeDB(self._oversized(3))
        conf = {"apex_access_log_max_payload_bytes": 100, "apex_access_log_purge_batch_size": 2}
        first, _ = _run(fake, conf)
        second, _ = _run(fake, conf)
        self.assertEqual(first["deleted"], 3)
        self.assertEqual(second["deleted"], 0)
        self.assertEqual(second["batches"], 0)
        self.assertFalse(second["truncated"])


class TestDryRun(unittest.TestCase):
    def test_dry_run_deletes_nothing_and_returns_only_names_sizes_and_counts(self):
        secret = "SENSITIVE-EXPORT-BODY"
        fake = _FakeDB({"AL-big": {"page": secret + _payload(200), "filters": _payload(30)}})
        result, _ = _run(fake, {"apex_access_log_max_payload_bytes": 100}, dry_run=True)

        self.assertTrue(result["dry_run"])
        self.assertEqual(fake.deleted_batches, [], "a dry run must not delete")
        self.assertIn("AL-big", fake.rows)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["total_bytes"], len(secret) + 200 + 30)

        record = result["records"][0]
        self.assertEqual(tuple(record), mod.AUDIT_FIELDS)
        self.assertEqual(record["name"], "AL-big")
        self.assertEqual(record["page_bytes"], len(secret) + 200)
        self.assertEqual(record["filters_bytes"], 30)
        self.assertEqual(record["columns_bytes"], 0)
        self.assertNotIn(secret, repr(result), "audit output must carry no payload body")


class TestFailureHandling(unittest.TestCase):
    def test_failure_rolls_the_whole_run_back_reraises_and_logs_no_payload(self):
        secret = "SENSITIVE-EXPORT-BODY"
        names = [f"AL-{index}" for index in range(4)]
        fake = _FakeDB({name: {"page": secret + _payload(200)} for name in names})
        # First batch deletes cleanly, the second one fails.
        fake.fail_on_batch = 1

        with mock.patch.object(mod, "frappe") as frappe_mock:
            frappe_mock.db = fake
            frappe_mock.conf = {
                "apex_access_log_max_payload_bytes": 100,
                "apex_access_log_purge_batch_size": 2,
            }
            with self.assertRaises(RuntimeError):
                mod.purge_oversized_access_logs()

            frappe_mock.log_error.assert_called_once()
            message = frappe_mock.log_error.call_args.kwargs["message"]
            self.assertNotIn(secret, message, "the failure log must carry no payload body")

        self.assertEqual(fake.rollbacks, 1)
        self.assertEqual(len(fake.deleted_batches), 1, "only the batch before the failure ran")
        self.assertEqual(
            sorted(fake.rows),
            names,
            "an uncommitted run that fails must leave every row in place",
        )

    def test_job_never_commits(self):
        fake = _FakeDB({"AL-big": {"page": _payload(200)}})
        _run(fake, {"apex_access_log_max_payload_bytes": 100})
        self.assertEqual(fake.commits, 0)

        commit_calls = [
            node
            for node in ast.walk(ast.parse(inspect.getsource(mod)))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "commit"
        ]
        self.assertEqual(
            commit_calls,
            [],
            "the job must leave the commit to the scheduler transaction",
        )


class TestSettings(unittest.TestCase):
    def test_documented_defaults_apply_when_site_config_is_silent(self):
        fake = _FakeDB({})
        result, _ = _run(fake, {})
        self.assertEqual(result["threshold_bytes"], mod.DEFAULTS["apex_access_log_max_payload_bytes"])
        self.assertEqual(result["batch_size"], mod.DEFAULTS["apex_access_log_purge_batch_size"])
        self.assertEqual(result["max_batches"], mod.DEFAULTS["apex_access_log_purge_max_batches"])

    def test_non_positive_or_junk_values_fall_back_to_defaults(self):
        fake = _FakeDB({})
        result, _ = _run(fake, {"apex_access_log_max_payload_bytes": 0, "apex_access_log_purge_batch_size": "abc"})
        self.assertEqual(result["threshold_bytes"], mod.DEFAULTS["apex_access_log_max_payload_bytes"])
        self.assertEqual(result["batch_size"], mod.DEFAULTS["apex_access_log_purge_batch_size"])

    def test_site_config_overrides_are_honoured(self):
        fake = _FakeDB({})
        result, _ = _run(fake, {"apex_access_log_max_payload_bytes": 4096, "apex_access_log_purge_batch_size": 7})
        self.assertEqual(result["threshold_bytes"], 4096)
        self.assertEqual(result["batch_size"], 7)


class TestScanQuery(unittest.TestCase):
    def test_payload_columns_are_measured_never_selected(self):
        for field in mod.PAYLOAD_FIELDS:
            references = len(re.findall(rf"`{field}`", mod.SCAN_SQL))
            measured = len(re.findall(rf"OCTET_LENGTH\(`{field}`\)", mod.SCAN_SQL))
            self.assertGreater(references, 0, f"{field} must appear in the scan query")
            self.assertEqual(
                references,
                measured,
                f"every reference to `{field}` must be wrapped in OCTET_LENGTH, not selected",
            )

    def test_measured_columns_match_the_declared_payload_fields(self):
        measured = set(re.findall(r"OCTET_LENGTH\(`([a-z_]+)`\)", mod.SCAN_SQL))
        self.assertEqual(
            measured,
            set(mod.PAYLOAD_FIELDS),
            "SCAN_SQL and PAYLOAD_FIELDS must not drift apart",
        )

    def test_comparison_is_strict_and_parameterised(self):
        self.assertIn("> %(threshold)s", mod.SCAN_SQL)
        self.assertNotIn(">= %(threshold)s", mod.SCAN_SQL)
        self.assertIn("LIMIT %(limit)s", mod.SCAN_SQL)


class TestSchedulerRegistration(unittest.TestCase):
    def test_job_is_registered_at_23_00_cron(self):
        cron = apex.hooks.scheduler_events["cron"]
        self.assertIn("0 23 * * *", cron)
        self.assertIn(JOB_PATH, cron["0 23 * * *"])

    def test_registered_path_resolves_to_the_public_entry_point(self):
        module_path, _, attribute = JOB_PATH.rpartition(".")
        self.assertEqual(module_path, mod.__name__)
        self.assertTrue(callable(getattr(mod, attribute)))


if __name__ == "__main__":
    unittest.main()
