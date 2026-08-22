# Copyright (c) 2026, afmcoltd
"""What Facility Asset Movement Ledger guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``validate``. This is a
single-write audit memo: the engine inserts one row per submitted movement and posts a
separate negated reversal on cancel, so the original row must never be re-saved in
place. ``on_doctype_update``'s unique-index backstop is schema DDL run on migrate, not
document behaviour, and is out of scope for a document-level test.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]


class TestFacilityAssetMovementLedger(FrappeTestCase):
    def test_editing_an_already_persisted_row_is_refused(self):
        """The initial insert is accepted; any save after that is not."""
        record = frappe.copy_doc(
            frappe.get_test_records("Facility Asset Movement Ledger")[0]
        )
        record.insert()

        record.to_location = "Rewritten after the fact"
        with self.assertRaisesRegex(frappe.PermissionError, "cannot be edited"):
            record.save()
