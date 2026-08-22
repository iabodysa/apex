# Copyright (c) 2026, afmcoltd
"""What a Masar Worker Token guarantees, asserted against the DocType itself.

Patterned on frappe's own document-persistence tests (``frappe/tests/test_document.py``,
e.g. ``test_conflict_validation``): the subject here is a DB-level idempotence guarantee,
not a plain validation refusal.

There is no ``test_records.json`` for this DocType and none is added (fixed at 92 files).
The real, whitelisted creation door is ``issue_worker_link`` -> ``get_or_create_for_employee``,
so this test drives that door directly rather than constructing a
``Masar Worker Token`` row by hand — a hand-built row would skip ``authorize_issuance``
and the token-minting path entirely and prove nothing about the real one.

The guarantee: one Employee binds to exactly ONE token row. Calling the issuance door
twice for the same Employee (the desk action fired twice, a double-click, a retried
request) must return the SAME link, not mint a second row.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    issue_worker_link,
)

test_dependencies = ["Employee"]

_EMPLOYEE = "_T-Employee-00001"


class TestMasarWorkerToken(FrappeTestCase):
    def setUp(self):
        self.addCleanup(self._delete_issued_token)

    def _delete_issued_token(self):
        name = frappe.db.get_value("Masar Worker Token", {"employee": _EMPLOYEE}, "name")
        if name:
            frappe.delete_doc(
                "Masar Worker Token", name, force=True, ignore_permissions=True
            )

    def test_issuing_a_link_twice_for_the_same_employee_returns_one_row_not_two(self):
        """A double-click on "Issue Worker Link", or a retried request, must not hand
        the same worker two live tokens for the desk to track."""
        first = issue_worker_link(employee=_EMPLOYEE)
        self.assertEqual(
            frappe.db.count("Masar Worker Token", {"employee": _EMPLOYEE}), 1
        )

        second = issue_worker_link(employee=_EMPLOYEE)
        self.assertEqual(
            frappe.db.count("Masar Worker Token", {"employee": _EMPLOYEE}), 1
        )

        # regenerate=0 (the default) re-shares the SAME token rather than rotating it.
        self.assertEqual(second["token"], first["token"])

    def test_issuing_with_regenerate_rotates_the_token_without_adding_a_row(self):
        """``regenerate=1`` is how a lost link is invalidated on purpose — it must
        replace the existing row's token, never add a second row for the same
        Employee."""
        first = issue_worker_link(employee=_EMPLOYEE)

        second = issue_worker_link(employee=_EMPLOYEE, regenerate=1)

        self.assertEqual(
            frappe.db.count("Masar Worker Token", {"employee": _EMPLOYEE}), 1
        )
        self.assertNotEqual(second["token"], first["token"])
