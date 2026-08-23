# Copyright (c) 2026, afmcoltd
"""Tests for Custody Return's issue-progress classifier and issue-line matcher.

Patterned on test_lease.py. ``_progress_from`` is pure arithmetic over two
plain dicts -- no document, no DB. ``_link_issue_lines`` reads the linked
Custody Issue's child rows via ``frappe.get_all``; that one call is mocked so
the serial-first / single-candidate-article matching is exercised without a
real Custody Issue.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.custody_return.custody_return import (
    _link_issue_lines,
    _progress_from,
)


class TestProgressFrom(FrappeTestCase):
    def test_every_issued_article_fully_returned_reads_as_returned(self):
        self.assertEqual(_progress_from({"A": 2, "B": 1}, {"A": 2, "B": 1}), "Returned")

    def test_some_but_not_all_returned_reads_as_partially_returned(self):
        self.assertEqual(_progress_from({"A": 2, "B": 1}, {"A": 2}), "Partially Returned")

    def test_nothing_returned_reads_as_issued(self):
        self.assertEqual(_progress_from({"A": 2}, {}), "Issued")

    def test_an_over_return_still_reads_as_fully_returned(self):
        self.assertEqual(_progress_from({"A": 2}, {"A": 5}), "Returned")

    def test_no_issued_articles_at_all_reads_as_issued_not_returned(self):
        self.assertEqual(_progress_from({}, {}), "Issued")


class TestLinkIssueLines(FrappeTestCase):
    def _rows(self):
        return [
            frappe._dict(name="CII-1", article="ART-A", serial_no="SN-1"),
            frappe._dict(name="CII-2", article="ART-B", serial_no=""),
            frappe._dict(name="CII-3", article="ART-B", serial_no=""),
        ]

    def test_a_serial_match_wins_outright(self):
        doc = frappe.new_doc("Custody Return")
        doc.custody_issue = "CI-0001"
        doc.append("items", {"article": "ART-A", "serial_no": "SN-1"})
        with patch.object(frappe, "get_all", return_value=self._rows()):
            _link_issue_lines(doc)
        self.assertEqual(doc.items[0].custody_issue_item, "CII-1")

    def test_an_ambiguous_unserialised_article_resolves_to_nothing(self):
        doc = frappe.new_doc("Custody Return")
        doc.custody_issue = "CI-0001"
        doc.append("items", {"article": "ART-B", "serial_no": ""})
        with patch.object(frappe, "get_all", return_value=self._rows()):
            _link_issue_lines(doc)
        self.assertIsNone(doc.items[0].custody_issue_item)

    def test_a_single_candidate_unserialised_article_resolves(self):
        doc = frappe.new_doc("Custody Return")
        doc.custody_issue = "CI-0001"
        doc.append("items", {"article": "ART-A", "serial_no": ""})
        with patch.object(frappe, "get_all", return_value=self._rows()):
            _link_issue_lines(doc)
        self.assertEqual(doc.items[0].custody_issue_item, "CII-1")
