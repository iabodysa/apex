# Copyright (c) 2026, afmcoltd
"""Movement Cost Transfer's own contract: it moves cost between two DIFFERENT projects.

The fixtures live in `_make_test_records` rather than `test_records.json` because the transfer
needs two distinct Projects and ERPNext ships exactly one test Project (`_T-Project-00001`, from
`erpnext/projects/doctype/project/test_records.json`). A JSON fixture can only name records some
other file already creates, so the second Project is created here — the hook
`make_test_records_for_doctype` (frappe/test_runner.py:393-394) prefers `_make_test_records` over
every other source, which is exactly what a fixture that has to compute something is for.
"""

from __future__ import annotations

import frappe
from frappe.test_runner import make_test_objects
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_project

test_dependencies = ["Project", "Salis Vehicle", "Salis Driver"]

FROM_PROJECT = "_T-Project-00001"
TARGET_PROJECT_TITLE = "_T Cost Transfer Target"


def _target_project():
    """The second Project the transfer moves cost INTO.

    Project autonames from its series, so the created row is `PROJ-####` and never the title
    passed in; `make_project` returns the real name, which is the value a Link field needs.
    """
    return make_project(TARGET_PROJECT_TITLE)


def _make_test_records(verbose=None):
    """Build the transfer fixtures after their second Project exists."""
    to_project = _target_project()
    records = [
        {
            "doctype": "Movement Cost Transfer",
            "transfer_date": "2026-03-01",
            "from_project": FROM_PROJECT,
            "to_project": to_project,
            "amount": 1500,
            "reason": "Shared shuttle reallocated for March",
        },
        {
            "doctype": "Movement Cost Transfer",
            "transfer_date": "2026-04-01",
            "from_project": to_project,
            "to_project": FROM_PROJECT,
            "amount": 400,
            "reason": "Partial reversal after the shuttle returned",
        },
    ]
    return make_test_objects("Movement Cost Transfer", records, verbose, commit=True)


class TestMovementCostTransfer(FrappeTestCase):
    def test_the_two_projects_must_differ(self):
        transfer = frappe.get_doc(
            {
                "doctype": "Movement Cost Transfer",
                "transfer_date": "2026-05-01",
                "from_project": FROM_PROJECT,
                "to_project": FROM_PROJECT,
                "amount": 100,
                "reason": "same project on both sides",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            transfer.insert(ignore_permissions=True)

    def test_a_transfer_between_two_projects_is_accepted(self):
        transfer = frappe.get_doc(
            {
                "doctype": "Movement Cost Transfer",
                "transfer_date": "2026-05-02",
                "from_project": FROM_PROJECT,
                "to_project": _target_project(),
                "amount": 250,
                "reason": "shuttle share for May",
            }
        ).insert(ignore_permissions=True)
        self.assertNotEqual(transfer.from_project, transfer.to_project)
