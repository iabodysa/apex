# Copyright (c) 2026, AFMCO and contributors
"""Guard: the bed-occupancy indexes are declared by the fresh-install path.

Frappe calls a DocType module's ``on_doctype_update`` when the table is created
during app sync and again on every ``bench migrate``, so it is the one delivery
path that reaches BOTH a brand-new site and an already-installed one. This test
pins the contract that path declares — which indexes, over which ordered columns.

No live site or DB is needed: the DDL boundary (``add_index_guarded``) is mocked,
so what is asserted is the delegation itself, never the SQL.
"""

import unittest
from unittest import mock

from apex.apex_core.utils import ledger_index
from apex.habitat.doctype.housing_assignment import housing_assignment

_EXPECTED_INDEXES = {
    "idx_asgn_bed": ["bed"],
    "idx_asgn_bed_active": ["bed", "docstatus", "check_out_date"],
}


def _index_calls(add_index_mock):
    """{index_name: [column, ...]} recorded off the mocked helper, so an assertion
    reads as the index contract rather than as call plumbing."""
    calls = {}
    for call in add_index_mock.call_args_list:
        doctype, fields, index_name = call.args
        assert doctype == "Housing Assignment", f"unexpected doctype {doctype!r}"
        calls[index_name] = list(fields)
    return calls


class TestFreshInstallHookDeclaresTheIndexes(unittest.TestCase):
    def test_on_doctype_update_declares_both_bed_indexes(self):
        """``on_doctype_update`` is the only path that indexes a brand-new site, so
        it must declare both bed indexes over exactly the columns the occupancy
        lookup reads."""
        with mock.patch.object(
            ledger_index, "add_index_guarded", return_value=True
        ) as add_index:
            housing_assignment.on_doctype_update()

        self.assertEqual(_index_calls(add_index), _EXPECTED_INDEXES)


if __name__ == "__main__":
    unittest.main()
