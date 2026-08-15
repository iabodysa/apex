# Copyright (c) 2026, afmcoltd
"""The duplicate-rent guard has to read the table it is guarding, under a lock.

``create_rent_payment`` locks the Lease row, but the row it is protecting against is a
Payment Entry. A plain SELECT is answered from the transaction's consistent snapshot,
which was taken before the lock was ever waited on — so the second concurrent click
passed the lock, looked, saw nothing, and raised a second draft Payment Entry for one
instalment. Only a locking read on Payment Entry itself sees the committed row.

``get_rent_payment_status`` must stay non-locking: it is a read-only status endpoint and
has no write to protect.
"""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.habitat.doctype.lease import lease_payment


class TestRentPaymentDuplicateProbeLocks(TestCase):
    def _probe_kwargs(self, endpoint, *args):
        fake = MagicMock()
        fake.db.get_value.return_value = "PE-1"
        lease_doc = MagicMock(company="C", landlord="L")
        lease_doc.name = "LEASE-1"
        row = frappe._dict(due_date="2026-09-01", amount=1000)

        with (
            patch.object(lease_payment, "frappe", fake),
            patch.object(lease_payment, "_load_eligible_lease", return_value=lease_doc),
            patch.object(lease_payment, "_instalment", return_value=row),
            patch.object(lease_payment, "payable_allocation") as allocation,
        ):
            allocation.PAYMENT_ENTRY_DOCTYPE = "Payment Entry"
            allocation.settlement_of.return_value = {}
            allocation.payable_count.return_value = 0
            getattr(endpoint, "__wrapped__", endpoint)(*args)

        probes = [
            call
            for call in fake.db.get_value.call_args_list
            if call.args and call.args[0] == "Payment Entry"
        ]
        self.assertEqual(len(probes), 1, "the instalment is probed exactly once")
        return probes[0]

    def test_the_create_path_probes_payment_entry_under_a_lock(self):
        probe = self._probe_kwargs(
            lease_payment.create_rent_payment, "LEASE-1", "2026-09-01"
        )
        self.assertTrue(
            probe.kwargs.get("for_update"),
            "an unlocked probe reads a snapshot older than the Lease lock it sits behind",
        )

    def test_the_status_path_takes_no_lock(self):
        probe = self._probe_kwargs(
            lease_payment.get_rent_payment_status, "LEASE-1", "2026-09-01"
        )
        self.assertFalse(
            probe.kwargs.get("for_update"),
            "a read-only status endpoint must not lock rows it never writes",
        )
