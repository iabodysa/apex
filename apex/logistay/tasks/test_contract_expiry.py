# Copyright (c) 2026, AFMCO and contributors
"""The Telecom Contract expiry watch: the flip a submitted document can never give itself.

``_sync_status`` only runs inside ``validate``, so a contract Active at submit time never
revisits its own status once the period ends — nothing calls ``validate`` on a docstatus-1
document again. Siteless by construction, like the sibling SIM watch test: the contract
table below is data and nothing is written to a real site.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from apex.logistay.tasks import contract_expiry

CONTRACTS = [
    {"name": "TEL-CTR-0001", "docstatus": 1, "status": "Active", "contract_end_date": "2020-01-01"},
    {"name": "TEL-CTR-0002", "docstatus": 1, "status": "Active", "contract_end_date": "2999-01-01"},
]


def _matches(row, filters):
    for field, want in filters.items():
        have = row.get(field)
        if isinstance(want, list):
            operator, value = want
            if operator == "<" and not have < value:
                return False
            if operator == ">" and not have > value:
                return False
        elif have != want:
            return False
    return True


class ContractExpiryWatchCase(unittest.TestCase):
    def setUp(self):
        self.flipped = []

        def _get_all(doctype, **kwargs):
            assert doctype == "Telecom Contract"
            filters = kwargs.get("filters") or {}
            return [
                contract_expiry.frappe._dict({k: row[k] for k in kwargs["fields"]})
                for row in CONTRACTS
                if _matches(row, filters)
            ]

        def _set_value(doctype, name, field, value):
            self.flipped.append((name, field, value))

        self._start(patch.object(contract_expiry.frappe, "get_all", side_effect=_get_all))
        self._start(patch.object(contract_expiry.frappe.db, "set_value", side_effect=_set_value))
        self._start(patch.object(contract_expiry, "today", return_value="2026-08-16"))

    def _start(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)


class TestThePastDueContractIsFlipped(ContractExpiryWatchCase):
    def test_a_submitted_active_contract_past_its_end_date_is_flipped_to_expired(self):
        contract_expiry.contract_expiry_watchlist()
        self.assertIn(("TEL-CTR-0001", "status", "Expired"), self.flipped)

    def test_a_contract_not_yet_past_its_end_date_is_left_alone(self):
        contract_expiry.contract_expiry_watchlist()
        names_touched = {name for name, _field, _value in self.flipped}
        self.assertNotIn(
            "TEL-CTR-0002", names_touched,
            "a contract whose period is still open must not be flipped to Expired",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
