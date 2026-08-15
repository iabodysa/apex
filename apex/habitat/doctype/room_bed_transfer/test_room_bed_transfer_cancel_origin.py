# Copyright (c) 2026, afmcoltd
"""``before_cancel`` must guard BOTH ends of the swap, not only the destination.

``on_cancel`` writes ``from_bed`` back to Occupied unconditionally. If somebody
else has moved into that bed since the transfer freed it, the reversal produces
two live assignments on one bed — the phantom occupancy ``before_cancel`` exists
to prevent. The destination check alone never sees it.
"""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.habitat.doctype.room_bed_transfer import room_bed_transfer


def _raising_frappe() -> MagicMock:
    fake = MagicMock()

    def throw(message, exc=None, **_kwargs):
        raise (exc or frappe.ValidationError)(message)

    fake.throw.side_effect = throw
    return fake


def _transfer():
    doc = MagicMock(assignment="HA-1", from_bed="BED-FROM", to_bed="BED-TO")
    return doc


def _live_assignment():
    return frappe._dict(docstatus=1, check_out_date=None, bed="BED-TO")


class TestRoomBedTransferCancelChecksOrigin(TestCase):
    def _run(self, origin_status):
        fake = _raising_frappe()
        fake.db.get_value.side_effect = [_live_assignment(), origin_status]
        with (
            patch.object(room_bed_transfer, "frappe", fake),
            patch.object(room_bed_transfer, "_", side_effect=lambda message: message),
        ):
            room_bed_transfer.before_cancel(_transfer())
        return fake

    def test_cancel_is_allowed_while_the_origin_bed_is_still_free(self):
        fake = self._run("Available")
        self.assertEqual(
            fake.db.get_value.call_args.args[:3],
            ("Bed", "BED-FROM", "status"),
            "the origin bed status must be the second read",
        )
        self.assertTrue(
            fake.db.get_value.call_args.kwargs.get("for_update"),
            "the origin read must lock, or the check and the reversal see different rows",
        )

    def test_cancel_is_refused_once_the_origin_bed_is_taken(self):
        for origin_status in ("Occupied", "Out of Service"):
            with self.subTest(origin_status=origin_status):
                with self.assertRaises(frappe.ValidationError):
                    self._run(origin_status)
