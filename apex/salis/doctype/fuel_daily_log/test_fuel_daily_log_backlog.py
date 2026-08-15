# Copyright (c) 2026, afmcoltd
"""Regression: a Fuel Daily Log is accrued because it is unledgered, not because it
is recent.

``accrue_fuel_consumption`` selected Fuel Daily Logs by a fixed two-day ``log_date``
window. Two rows of real fuel then never reached the Fuel Consumption Ledger at all:
a log backdated further than yesterday was out of scope on every run that would ever
happen, and one missed scheduler day put that whole day's logs permanently out of
reach. Nothing retried them, because the window moved on. The Fuel Request half of
the same job already drained its backlog off a ``ledgered`` flag; the log half now
does too.

The last test grades the DocType JSON, because the loop is only as good as the column
it filters on: a ``ledgered`` that is not ``no_copy`` would let an amended log arrive
pre-flagged and never be accrued, and one without ``default: 0`` would leave the
filter matching nothing.

Pure unit tests: the engine's ``frappe`` handle and its two ledger helpers are
replaced, so no site and no tables.
"""

from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from apex.salis import fuel_engine


DOCTYPE_JSON = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "fuel_daily_log.json"
)


def _log(name, vehicle="VEH-1", log_date="2020-01-01"):
    """A log dated years back — the case the two-day window could never reach."""
    return SimpleNamespace(
        name=name, vehicle=vehicle, driver="DRV-1", log_date=log_date, litres=40.0, amount=200.0
    )


def _run(pages, *, already_ledgered=False, insert_raises=False):
    """Drive the accrual job and report the reads and the flag writes it made."""
    reads = []
    flagged = []

    def get_all(doctype, **kwargs):
        reads.append((doctype, kwargs))
        if doctype != "Fuel Daily Log":
            return []
        return pages.pop(0) if pages else []

    def set_value(doctype, name, field, value, **kwargs):
        flagged.append((doctype, name, field, value))

    mock_frappe = mock.MagicMock()
    mock_frappe.get_all.side_effect = get_all
    mock_frappe.db.set_value.side_effect = set_value

    insert = mock.Mock(side_effect=Exception("boom") if insert_raises else None)

    with mock.patch.object(fuel_engine, "frappe", mock_frappe), mock.patch.object(
        fuel_engine, "_ledger_exists", return_value=already_ledgered
    ), mock.patch.object(fuel_engine, "_insert_ledger_row", insert), mock.patch(
        "frappe.utils.now_datetime", mock.Mock(return_value="2026-08-15 00:00:00")
    ):
        fuel_engine.accrue_fuel_consumption()

    return reads, flagged, insert


class TestFuelDailyLogBacklog(unittest.TestCase):
    def _log_read(self, reads):
        return next(kw for doctype, kw in reads if doctype == "Fuel Daily Log")

    def test_the_selection_is_the_flag_and_never_a_date_window(self):
        reads, _flagged, _insert = _run([[_log("FDL-1")]])
        filters = self._log_read(reads)["filters"]
        self.assertEqual(0, filters.get("ledgered"))
        self.assertNotIn(
            "log_date",
            filters,
            "a date window drops a backdated log instead of deferring it",
        )

    def test_a_years_old_unledgered_log_is_still_accrued(self):
        _reads, flagged, insert = _run([[_log("FDL-OLD", log_date="2020-01-01")]])
        insert.assert_called_once()
        self.assertEqual("FDL-OLD", insert.call_args.kwargs["source_name"])
        self.assertEqual(
            "2020-01",
            insert.call_args.kwargs["period_month"],
            "the row must land in the period it was fuelled, not the run's month",
        )
        self.assertIn(("Fuel Daily Log", "FDL-OLD", "ledgered", 1), flagged)

    def test_a_log_already_in_the_ledger_is_flagged_not_posted_twice(self):
        """The flag starts at 0 on every existing row, so the first run after this
        change re-reads history — ``_ledger_exists`` is what keeps it from re-posting."""
        _reads, flagged, insert = _run([[_log("FDL-1")]], already_ledgered=True)
        insert.assert_not_called()
        self.assertIn(("Fuel Daily Log", "FDL-1", "ledgered", 1), flagged)

    def test_a_log_with_no_vehicle_is_flagged_so_it_stops_being_re_read(self):
        _reads, flagged, insert = _run([[_log("FDL-NOVEH", vehicle=None)]])
        insert.assert_not_called()
        self.assertIn(("Fuel Daily Log", "FDL-NOVEH", "ledgered", 1), flagged)

    def test_a_page_that_only_fails_ends_the_pass(self):
        """Without the progress check the same failing page is read forever: the flag
        is the cursor, and a row that raised never gets one."""
        pages = [[_log("FDL-BAD")] for _ in range(50)]
        reads, flagged, _insert = _run(pages, insert_raises=True)
        log_reads = [doctype for doctype, _kw in reads if doctype == "Fuel Daily Log"]
        self.assertEqual(1, len(log_reads), "the job re-read a page it could not drain")
        self.assertEqual([], flagged)

    def test_the_doctype_declares_the_flag_the_loop_filters_on(self):
        with open(DOCTYPE_JSON, encoding="utf-8") as fh:
            meta = json.load(fh)
        field = next(f for f in meta["fields"] if f["fieldname"] == "ledgered")
        self.assertEqual("Check", field["fieldtype"])
        self.assertEqual("0", field["default"])
        self.assertEqual(1, field["no_copy"], "an amended log must not arrive pre-flagged")
        self.assertEqual(1, field["read_only"])
        self.assertEqual(1, field["hidden"])
        self.assertIn("ledgered", meta["field_order"])


if __name__ == "__main__":
    unittest.main()
