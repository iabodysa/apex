# Copyright (c) 2026, afmcoltd


import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.worklist.action_inbox import _drop_stale

FAKE_DOCTYPE = "Zzz Nonexistent Test DocType"
FAKE_REFERENCE = "FAKE-ACTION-INBOX-TEST-0001"


class TestDropStaleDeletesActionsForAMissingDocType(FrappeTestCase):
    def test_the_row_is_deleted_not_merely_hidden(self):
        wa = frappe.get_doc(
            {
                "doctype": "Workflow Action",
                "status": "Open",
                "reference_doctype": FAKE_DOCTYPE,
                "reference_name": FAKE_REFERENCE,
                "user": frappe.session.user,
                "workflow_state": "Pending",
            }
        )
        wa.flags.ignore_links = True
        wa.insert(ignore_permissions=True)
        self.assertTrue(frappe.db.exists("Workflow Action", wa.name))

        rows = [
            {
                "name": wa.name,
                "reference_doctype": FAKE_DOCTYPE,
                "reference_name": FAKE_REFERENCE,
                "workflow_state": "Pending",
                "creation": wa.creation,
            }
        ]
        kept = _drop_stale(rows)

        self.assertEqual(kept, [])
        self.assertFalse(frappe.db.exists("Workflow Action", wa.name))
