# Copyright (c) 2026, afmcoltd
"""What Maintenance Cost Ledger guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``on_update``. This is a
machine-written cost trail: the maintenance engine inserts one row per completed
procurement item and reverses one with a negative mirror row, never an edit, so an
already-persisted row must refuse any later save. ``on_doctype_update``'s unique-index
backstop is schema DDL run on migrate, not document behaviour, and is out of scope for a
document-level test.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]


class TestMaintenanceCostLedger(FrappeTestCase):
    def test_editing_an_already_persisted_row_is_refused(self):
        """The initial insert is accepted; any save after that is not."""
        record = frappe.copy_doc(frappe.get_test_records("Maintenance Cost Ledger")[0])
        record.insert()

        record.item_description = "Rewritten after the fact"
        with self.assertRaisesRegex(frappe.ValidationError, "immutable"):
            record.save()
