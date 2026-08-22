# Copyright (c) 2026, afmcoltd
"""What Cleaning Compliance Ledger guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is a machine-written,
single-write audit memo. ``on_update`` blocks any edit past the initial insert, and
``on_trash`` blocks delete for anyone but a System Manager even when a caller passes
``ignore_permissions`` — the DocPerm alone is not enough, because that flag skips DocPerm
entirely, so the role check is read directly in the controller.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building", "Room"]


class TestCleaningComplianceLedger(FrappeTestCase):
    def test_editing_an_already_persisted_row_is_refused(self):
        """The initial insert is accepted; any save after that is not."""
        record = frappe.copy_doc(frappe.get_test_records("Cleaning Compliance Ledger")[0])
        record.insert()

        record.skip_reason = "Rewritten after the fact"
        with self.assertRaisesRegex(frappe.ValidationError, "immutable"):
            record.save()

    def test_delete_is_refused_to_a_non_system_manager_even_with_ignore_permissions(self):
        """Bypassing DocPerm with ignore_permissions must not bypass the role check itself."""
        record = frappe.copy_doc(frappe.get_test_records("Cleaning Compliance Ledger")[0])
        record.insert()

        with self.set_user("test2@example.com"):
            self.assertNotIn("System Manager", frappe.get_roles())
            with self.assertRaisesRegex(frappe.ValidationError, "cannot be deleted"):
                frappe.delete_doc(
                    "Cleaning Compliance Ledger", record.name, ignore_permissions=True
                )

        self.assertTrue(
            frappe.db.exists("Cleaning Compliance Ledger", record.name),
            "a refused delete must leave the row standing",
        )

    def test_delete_is_allowed_to_a_system_manager(self):
        """The role the guard names is the one role it must actually let through."""
        record = frappe.copy_doc(frappe.get_test_records("Cleaning Compliance Ledger")[0])
        record.insert()

        frappe.delete_doc("Cleaning Compliance Ledger", record.name, ignore_permissions=True)

        self.assertFalse(frappe.db.exists("Cleaning Compliance Ledger", record.name))
