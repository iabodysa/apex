# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.custody_issue.custody_issue import (
    _holder,
    _set_expected_return_date,
    validate_serialized_rows,
)


class TestHolder(FrappeTestCase):
    def test_a_legacy_employee_link_wins_over_the_party_pair(self):
        doc = frappe._dict(
            issued_to_employee="HR-EMP-0001", party_type="Temporary Worker", party="TW-0001"
        )
        self.assertEqual(_holder(doc), ("Employee", "HR-EMP-0001"))

    def test_no_employee_link_falls_back_to_the_party_pair(self):
        doc = frappe._dict(
            issued_to_employee=None, party_type="Temporary Worker", party="TW-0001"
        )
        self.assertEqual(_holder(doc), ("Temporary Worker", "TW-0001"))


class TestSetExpectedReturnDate(FrappeTestCase):
    def _doc(self, expected_return_date=None):
        doc = frappe.new_doc("Custody Issue")
        doc.issue_date = "2026-01-01"
        doc.expected_return_date = expected_return_date
        doc.append("items", {"article": "ART-1"})
        doc.append("items", {"article": "ART-2"})
        return doc

    def test_the_default_uses_the_longest_category_window_across_every_line(self):
        doc = self._doc()
        with patch.object(
            frappe.db, "get_value", side_effect=["CAT-SHORT", 10, "CAT-LONG", 30]
        ):
            _set_expected_return_date(doc)
        self.assertEqual(str(doc.expected_return_date), "2026-01-31")

    def test_an_operator_entered_date_is_never_overwritten(self):
        doc = self._doc(expected_return_date="2026-03-01")
        with patch.object(frappe.db, "get_value") as mock_get_value:
            _set_expected_return_date(doc)
            mock_get_value.assert_not_called()
        self.assertEqual(str(doc.expected_return_date), "2026-03-01")


class TestValidateSerializedRows(FrappeTestCase):
    def _doc(self, qty=1, serial_no="SN-1", article="ART-SERIAL"):
        doc = frappe.new_doc("Custody Issue")
        doc.append("items", {"article": article, "qty": qty, "serial_no": serial_no})
        return doc

    def test_a_serialized_article_without_a_serial_is_refused(self):
        doc = self._doc(serial_no="")
        with patch.object(frappe, "get_all", return_value=["ART-SERIAL"]):
            with self.assertRaises(frappe.ValidationError):
                validate_serialized_rows(doc)

    def test_a_serialized_article_with_qty_over_one_is_refused(self):
        doc = self._doc(qty=2)
        with patch.object(frappe, "get_all", return_value=["ART-SERIAL"]):
            with self.assertRaises(frappe.ValidationError):
                validate_serialized_rows(doc)

    def test_a_non_serialized_article_is_never_checked(self):
        doc = self._doc(serial_no="")
        with patch.object(frappe, "get_all", return_value=[]):
            validate_serialized_rows(doc)
