# Copyright (c) 2026, afmcoltd
"""What a Safety Finding Ledger guarantees, asserted against the DocType itself.

Patterned on frappe's own document-persistence tests (``frappe/tests/test_document.py``,
``test_conflict_validation``). This is a read-only, machine-written immutable audit memo —
no DocPerm grants create/write/delete to any role, and its own controller enforces that at
the document level too: an existing row can never be edited, and can never be deleted
(only a reversal row may negate it, posted elsewhere by the safety engine).
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSafetyFindingLedger(FrappeTestCase):
    def test_a_fresh_row_inserts_and_editing_it_afterward_is_refused(self):
        """``on_update`` only blocks a change to a row that ALREADY exists — ``is_new()``
        lets the original insert through — so this pins both halves: the insert succeeds,
        and any edit made after it is refused."""
        row = frappe.copy_doc(frappe.get_test_records("Safety Finding Ledger")[0])
        row.insert()
        self.assertEqual(row.severity, "High")

        row.reload()
        row.status = "Resolved"
        with self.assertRaisesRegex(frappe.ValidationError, "immutable"):
            row.save()

    def test_deleting_a_row_is_refused(self):
        """A finding must never disappear from the audit trail; cancelling the Safety
        Round that posted it is the only sanctioned way to negate it, via a reversal row
        posted elsewhere — never a delete."""
        row = frappe.copy_doc(frappe.get_test_records("Safety Finding Ledger")[1])
        row.insert()

        with self.assertRaisesRegex(frappe.ValidationError, "cannot be deleted"):
            frappe.delete_doc("Safety Finding Ledger", row.name)
