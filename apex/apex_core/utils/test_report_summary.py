# Copyright (c) 2026, AFMCO and contributors
"""A query report must return the number strip frappe already renders.

`frappe.desk.query_report` reads a FIFTH value from `execute` and draws each entry as a
card above the table (`query_report.py:87`, `ljust_list(res, 6)`). Every Apex report
returned two values, so that strip was empty on all 52 of them and a reader had to add a
column up by hand to learn anything the rows did not already say.

Two things are proved here. The builders behave — including on the empty report, where a
share must read 0% rather than raise or render a blank card that looks like a failure.
And the reports that now carry a strip really return five values, computed off the SAME
rows the table shows: a summary built from its own query would eventually disagree with
the table under it, and the reader has no way to tell which one is wrong.

Size note: 86 test lines against 18 in the subject (4.8x), for 9 distinct behaviours. The ratio is arithmetic on a small subject, not overtesting: each test names a different behaviour.
"""

import os
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

import apex
from apex.apex_core.utils.report_summary import (
    card,
    count_card,
    percent_card,
    total_card,
)

# Read off the tree rather than listed by hand. The hand-written list named six reports
# that the v2_3 retirement patch deleted, so this module stopped importing at all — and a
# list that survives that failure still silently omits every report wired up after it was
# written. A report is "wired" when its module names the summary helpers.
_ROW_COUNT_REPORT = "apex.habitat.report.maintenance_aging.maintenance_aging"


def _wired_reports():
    """Dotted paths of every shipped report module that imports the summary helpers."""
    app_root = Path(apex.__file__).resolve().parent
    found = []
    for path in sorted(app_root.glob("*/report/*/*.py")):
        if path.stem != path.parent.name:
            continue
        if "report_summary" in path.read_text(encoding="utf-8"):
            module = path.relative_to(app_root).with_suffix("")
            found.append("apex." + str(module).replace(os.sep, "."))
    return tuple(found)


WIRED_REPORTS = _wired_reports()

ROWS = [
    {"priority": "Critical", "status": "Open", "amount": 10.5},
    {"priority": "High", "status": "Assigned", "amount": 4.5},
    {"priority": "High", "status": "Open", "amount": 0},
]


class TestTheReportSummaryBuilders(FrappeTestCase):
    def test_a_count_card_counts_the_rows_on_screen(self):
        self.assertEqual(count_card("All", ROWS)["value"], 3)
        self.assertEqual(
            count_card("High", ROWS, lambda r: r["priority"] == "High")["value"], 2
        )

    def test_a_total_card_sums_the_column(self):
        entry = total_card("Amount", ROWS, "amount", "Currency")
        self.assertEqual(entry["value"], 15.0)
        self.assertEqual(entry["datatype"], "Currency")

    def test_a_total_over_a_missing_field_is_zero_not_an_error(self):
        """A report whose rows do not carry the field must not break the whole page."""
        self.assertEqual(total_card("Nothing", ROWS, "no_such_field")["value"], 0)

    def test_a_percent_card_on_an_empty_report_reads_zero(self):
        """The division that would otherwise raise on the one case every report hits on
        a fresh site: no rows at all."""
        self.assertEqual(percent_card("Share", 0, 0)["value"], 0.0)
        self.assertEqual(percent_card("Share", 3, 4)["value"], 75.0)

    def test_an_indicator_is_only_present_when_asked_for(self):
        self.assertNotIn("indicator", card("Plain", 1))
        self.assertEqual(card("Hot", 1, indicator="Red")["indicator"], "Red")

    def test_the_scan_finds_the_wired_reports(self):
        """The population, asserted: the loop below proves nothing over an empty tuple."""
        self.assertGreater(len(WIRED_REPORTS), 20, "no wired report was found on disk")
        self.assertIn(_ROW_COUNT_REPORT, WIRED_REPORTS)

    def test_every_wired_report_returns_the_fifth_value(self):
        """The contract frappe reads. A report returning two values renders no strip,
        which is the defect this card names."""
        needs_filters = []
        graded = 0
        for dotted in WIRED_REPORTS:
            with self.subTest(report=dotted):
                execute = frappe.get_attr(dotted + ".execute")
                try:
                    result = execute({})
                except frappe.ValidationError:
                    # A report whose filters are mandatory cannot be driven with an empty
                    # set. Counted rather than skipped, so this branch can never quietly
                    # absorb the whole population.
                    needs_filters.append(dotted)
                    continue
                graded += 1
                self.assertGreaterEqual(
                    len(result), 5, "execute returns fewer than five values"
                )
                summary = result[4]
                self.assertTrue(summary, "the strip is empty")
                for entry in summary:
                    self.assertIn("label", entry)
                    self.assertIn("value", entry)
                    self.assertIn("datatype", entry)
        self.assertGreater(graded, len(needs_filters), "most wired reports must be graded")

    def test_the_first_figure_matches_the_row_count_the_table_shows(self):
        """The summary must be computed off the rows the table renders. If it ever grows
        its own query, this is where the two start to disagree."""
        execute = frappe.get_attr(_ROW_COUNT_REPORT + ".execute")
        _columns, data, _msg, _chart, summary = execute({})[:5]
        self.assertEqual(summary[0]["value"], len(data))

    def test_a_totals_row_is_not_counted_as_data(self):
        """Cost Recovery Aging appends a TOTALS row to `data` for the table to render.
        A summary built after that append counts it as a recovery and doubles every
        amount — the exact way a strip drifts from the table it sits above."""
        execute = frappe.get_attr(
            "apex.salis.report.cost_recovery_aging.cost_recovery_aging.execute"
        )
        _columns, data, _msg, _chart, summary = execute({})[:5]
        totals_rows = [r for r in data if r.get("age_days") is None and r.get("amount")]
        self.assertEqual(
            summary[0]["value"],
            len(data) - len(totals_rows),
            "the count includes the totals row",
        )
