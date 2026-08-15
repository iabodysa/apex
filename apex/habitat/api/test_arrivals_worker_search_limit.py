# Copyright (c) 2026, afmcoltd
"""The arrivals worker search has to exclude housed workers in the query.

``limit_page_length=15`` is applied by the database. Dropping housed workers from the
rows it returns shrinks a full page — and when the fifteen nearest matches are all
housed it returns nothing, so a supervisor searching for somebody to house is shown an
empty list while candidates exist.
"""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.habitat.api import arrivals_desk


def _rows(names):
    return [
        frappe._dict(
            name=name,
            employee_name=name,
            designation="Labourer",
            worker_name=name,
            passport_number="P" + name,
            expiry_date=None,
        )
        for name in names
    ]


class TestHousedWorkersAreExcludedInTheQuery(TestCase):
    def test_employee_search_asks_the_database_to_skip_housed_workers(self):
        fake = MagicMock()
        fake.get_all.return_value = _rows(["EMP-16"])

        with patch.object(arrivals_desk, "frappe", fake):
            results = arrivals_desk._employee_matches(
                "a", {"EMP-1", "EMP-2"}, {"EMP-3"}
            )

        filters = fake.get_all.call_args.kwargs["filters"]
        self.assertEqual(filters["name"], ["not in", ["EMP-1", "EMP-2", "EMP-3"]])
        self.assertEqual(
            fake.get_all.call_args.kwargs["limit_page_length"],
            15,
            "the page limit must still be the database's, not a post-filter's",
        )
        self.assertEqual([r["party"] for r in results], ["EMP-16"])

    def test_a_page_of_housed_employees_is_no_longer_returned_empty(self):
        """The defect, reproduced: fifteen housed matches came back and were all dropped."""
        fake = MagicMock()
        housed = {f"EMP-{n}" for n in range(1, 16)}
        fake.get_all.return_value = _rows(sorted(housed))

        with patch.object(arrivals_desk, "frappe", fake):
            results = arrivals_desk._employee_matches("a", housed, set())

        self.assertEqual(
            len(results),
            15,
            "rows the query was told to exclude must never reach the post-pass",
        )

    def test_temporary_worker_search_asks_the_database_to_skip_housed_workers(self):
        fake = MagicMock()
        fake.get_all.return_value = _rows(["TW-9"])
        fake.utils.formatdate.return_value = None

        with (
            patch.object(arrivals_desk, "frappe", fake),
            patch.object(arrivals_desk, "_", side_effect=lambda message: message),
            patch.object(arrivals_desk, "_expiry_days", return_value=None),
        ):
            results = arrivals_desk._temporary_worker_matches(
                "a", False, [], {"TW-1", "TW-2"}
            )

        filters = fake.get_all.call_args.kwargs["filters"]
        self.assertEqual(filters["name"], ["not in", ["TW-1", "TW-2"]])
        self.assertEqual([r["party"] for r in results], ["TW-9"])

    def test_no_exclusion_leaves_the_filter_alone(self):
        fake = MagicMock()
        fake.get_all.return_value = []

        with patch.object(arrivals_desk, "frappe", fake):
            arrivals_desk._employee_matches("a", set(), set())

        self.assertNotIn("name", fake.get_all.call_args.kwargs["filters"])
