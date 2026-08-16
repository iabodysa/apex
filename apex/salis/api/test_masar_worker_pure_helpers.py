# Copyright (c) 2026, AFMCO and contributors
"""Tests for masar_worker.py's pure shapers: functions that take plain values and
return plain values, documented in the module as runnable without a bench.

Each covers the one real branch or fallback the docstring promises:
``_iqama_of``'s field-name fallback, ``_worker_documents``'s conditional
inclusion, ``_request_status_timeline``'s settled-vs-active point, and
``_net_custody_items``'s net-zero drop and latest-issue tracking.
``_clean_adhoc_passengers`` needs frappe importable (``frappe.throw``/``_``), so
it runs under ``FrappeTestCase`` like the rest of the suite.
"""

from __future__ import annotations

from types import SimpleNamespace

from frappe.tests.utils import FrappeTestCase

from apex.salis.api.masar_worker import (
    _clean_adhoc_passengers,
    _iqama_of,
    _net_custody_items,
    _request_status_timeline,
    _worker_documents,
)


class TestIqamaOf(FrappeTestCase):
    def test_prefers_iqama_over_iqama_no(self):
        number, expiry = _iqama_of({"iqama": "1000000001", "iqama_no": "9999999999"})
        self.assertEqual(number, "1000000001")

    def test_falls_back_to_iqama_no_when_iqama_blank(self):
        number, expiry = _iqama_of({"iqama": "", "iqama_no": "1000000002"})
        self.assertEqual(number, "1000000002")

    def test_falls_back_to_valid_upto_when_iqama_expiry_blank(self):
        number, expiry = _iqama_of({"iqama_expiry": None, "valid_upto": "2027-01-01"})
        self.assertEqual(expiry, "2027-01-01")

    def test_neither_field_present_is_none(self):
        number, expiry = _iqama_of({})
        self.assertIsNone(number)
        self.assertIsNone(expiry)


class TestWorkerDocuments(FrappeTestCase):
    def test_iqama_listed_when_only_expiry_is_set(self):
        """An expiry alone still names a document that needs renewing."""
        docs = _worker_documents({"iqama": None, "iqama_expiry": "2027-01-01"})
        types = [d["type"] for d in docs]
        self.assertIn("iqama", types)

    def test_iqama_omitted_when_neither_number_nor_expiry_set(self):
        docs = _worker_documents({})
        types = [d["type"] for d in docs]
        self.assertNotIn("iqama", types)

    def test_passport_omitted_when_only_expiry_is_set(self):
        """A bare passport expiry names no document (unlike Iqama)."""
        docs = _worker_documents({"passport_number": "", "passport_expiry": "2027-01-01"})
        types = [d["type"] for d in docs]
        self.assertNotIn("passport", types)

    def test_passport_listed_when_number_is_set(self):
        docs = _worker_documents({"passport_number": "A1234567"})
        types = [d["type"] for d in docs]
        self.assertIn("passport", types)

    def test_this_check_can_fail_the_passport_omission_rule(self):
        """Negative control for test_passport_omitted_when_only_expiry_is_set: a
        real number DOES produce a passport entry, so the omission above is not
        a permanently-empty list."""
        docs = _worker_documents({"passport_number": "X", "passport_expiry": "2027-01-01"})
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["type"], "passport")


class TestRequestStatusTimeline(FrappeTestCase):
    def test_new_request_has_only_a_created_point(self):
        timeline = _request_status_timeline({"status": "New", "creation": "2026-01-01 10:00:00"})
        self.assertEqual([p["key"] for p in timeline], ["created"])

    def test_settled_status_adds_a_closed_point_not_a_current_point(self):
        timeline = _request_status_timeline(
            {"status": "Resolved", "creation": "2026-01-01 10:00:00", "closed_on": "2026-01-05"}
        )
        keys = [p["key"] for p in timeline]
        self.assertEqual(keys, ["created", "closed"])
        self.assertEqual(timeline[1]["timestamp"], "2026-01-05")

    def test_active_non_new_status_adds_a_current_point(self):
        timeline = _request_status_timeline(
            {"status": "In Progress", "creation": "2026-01-01 10:00:00", "modified": "2026-01-02"}
        )
        keys = [p["key"] for p in timeline]
        self.assertEqual(keys, ["created", "current"])

    def test_closed_point_falls_back_to_modified_when_closed_on_blank(self):
        timeline = _request_status_timeline(
            {
                "status": "Rejected",
                "creation": "2026-01-01 10:00:00",
                "closed_on": None,
                "modified": "2026-01-09",
            }
        )
        self.assertEqual(timeline[1]["timestamp"], "2026-01-09")


class TestNetCustodyItems(FrappeTestCase):
    def _row(self, building, item, qty, posting_date="2026-01-01", voucher_type="Custody Issue", voucher_no="CI-1"):
        return SimpleNamespace(
            building=building,
            item=item,
            item_name=item,
            uom="Nos",
            signed_qty=qty,
            posting_date=posting_date,
            voucher_type=voucher_type,
            voucher_no=voucher_no,
        )

    def test_a_fully_returned_bucket_is_dropped(self):
        """Issue then full return nets to zero and must not survive."""
        rows = [self._row("B1", "ART-1", 2), self._row("B1", "ART-1", -2)]
        buckets = _net_custody_items(rows)
        self.assertEqual(buckets, [])

    def test_a_partially_returned_bucket_survives_with_the_net_qty(self):
        rows = [self._row("B1", "ART-1", 3), self._row("B1", "ART-1", -1)]
        buckets = _net_custody_items(rows)
        self.assertEqual(len(buckets), 1)
        self.assertAlmostEqual(buckets[0]["qty"], 2.0)

    def test_reissue_after_return_dates_from_the_reissue(self):
        """received_date/_issue_voucher track the LATEST issue row, oldest-first input."""
        rows = [
            self._row("B1", "ART-1", 1, posting_date="2026-01-01", voucher_no="CI-OLD"),
            self._row("B1", "ART-1", -1, posting_date="2026-01-05", voucher_type="Custody Return", voucher_no="CR-1"),
            self._row("B1", "ART-1", 1, posting_date="2026-01-10", voucher_no="CI-NEW"),
        ]
        buckets = _net_custody_items(rows)
        self.assertEqual(len(buckets), 1)
        self.assertEqual(buckets[0]["received_date"], "2026-01-10")
        self.assertEqual(buckets[0]["_issue_voucher"], "CI-NEW")

    def test_distinct_buildings_are_not_merged(self):
        rows = [self._row("B1", "ART-1", 1), self._row("B2", "ART-1", 1)]
        buckets = _net_custody_items(rows)
        self.assertEqual(len(buckets), 2)


class TestCleanAdhocPassengers(FrappeTestCase):
    def test_missing_name_or_id_throws(self):
        import frappe

        with self.assertRaises(frappe.ValidationError):
            _clean_adhoc_passengers([{"full_name": "", "id_number": "1000000001"}])

    def test_unparseable_expiry_throws(self):
        import frappe

        with self.assertRaises(frappe.ValidationError):
            _clean_adhoc_passengers(
                [{"full_name": "Worker One", "id_number": "1000000001", "id_expiry": "not-a-date"}]
            )

    def test_valid_row_is_normalized_and_truncated(self):
        rows = _clean_adhoc_passengers(
            [{"full_name": "  Worker One  ", "id_number": " 1000000001 ", "nationality": "SA"}]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["full_name"], "Worker One")
        self.assertEqual(rows[0]["id_number"], "1000000001")
        self.assertEqual(rows[0]["nationality"], "SA")

    def test_json_string_input_is_parsed(self):
        rows = _clean_adhoc_passengers('[{"full_name": "Worker Two", "id_number": "1000000002"}]')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["full_name"], "Worker Two")

    def test_blank_input_returns_empty_list(self):
        self.assertEqual(_clean_adhoc_passengers(None), [])
        self.assertEqual(_clean_adhoc_passengers([]), [])
