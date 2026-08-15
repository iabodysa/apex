# Copyright (c) 2026, afmcoltd
"""``reject_handover`` decides on a status nobody is holding.

The reversal it authorises takes no lock either — ``_live_rows`` is a plain read — so two
rejections arriving together both saw the same live ledger rows, both mirrored them, and
the source store was credited twice for one shipment. ``confirm_handover`` already reads
its status with ``for_update``; this is the same read on the same row.
"""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.habitat.api import custody_handover


def _raising_frappe() -> MagicMock:
    fake = MagicMock()
    fake.PermissionError = frappe.PermissionError

    def throw(message, exc=None, **_kwargs):
        raise (exc or frappe.ValidationError)(message)

    fake.throw.side_effect = throw
    return fake


def _handover(status="Pending Receipt"):
    doc = MagicMock(docstatus=1, status=status)
    doc.name = "CH-1"
    return doc


def _call(endpoint, *args, **kwargs):
    return getattr(endpoint, "__wrapped__", endpoint)(*args, **kwargs)


class TestRejectHandoverLocksBeforeItDecides(TestCase):
    def _reject(self, doc, locked_status):
        fake = _raising_frappe()
        fake.get_doc.return_value = doc
        fake.db.get_value.return_value = locked_status
        with (
            patch.object(custody_handover, "frappe", fake),
            patch.object(custody_handover, "_", side_effect=lambda message: message),
            patch.object(custody_handover, "_require_receiving_side"),
            patch(
                "apex.habitat.doctype.accommodation_stock_ledger."
                "accommodation_stock_ledger.reverse_stock_entries"
            ) as reverse,
        ):
            _call(custody_handover.reject_handover, "CH-1", "Wrong items")
        return fake, reverse

    def test_the_status_is_read_under_a_row_lock(self):
        doc = _handover()
        fake, reverse = self._reject(doc, "Pending Receipt")

        self.assertEqual(
            fake.db.get_value.call_args.args[:3],
            (custody_handover.VOUCHER_TYPE, "CH-1", "status"),
        )
        self.assertTrue(
            fake.db.get_value.call_args.kwargs.get("for_update"),
            "without the lock two rejections both reverse the same ledger rows",
        )
        reverse.assert_called_once()

    def test_a_rejection_that_lost_the_race_is_refused_on_the_locked_row(self):
        """The in-memory doc still reads Pending Receipt; only the locked read is fresh."""
        for locked_status in ("Confirmed", "Rejected", "Cancelled"):
            with self.subTest(locked_status=locked_status):
                doc = _handover("Pending Receipt")
                with self.assertRaises(frappe.ValidationError):
                    self._reject(doc, locked_status)
                doc.db_set.assert_not_called()
