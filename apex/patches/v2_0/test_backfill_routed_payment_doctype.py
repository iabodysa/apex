# Copyright (c) 2026, AFMCO and contributors
"""Guard for the routed-payment link backfill.

The patch has to answer one question per historical row -- which table does this
payment name live in -- and its value is entirely in what it does when it CANNOT
answer. A guessed type is indistinguishable from a correct one once written, so an
unresolvable row must stay blank and be reported, never filled in with the most
likely candidate.

Both halves run in the same test: a resolvable row must actually be typed, or
"leaves it blank" would pass on a patch that simply does nothing.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.payment_router import (
    LINK_DOCTYPE_FIELD,
    LINK_NAME_FIELD,
    SOURCE_DOCTYPE,
)
from apex.patches.v2_0.backfill_routed_payment_doctype import execute

ROUTER = "Payment Routing Settings"


class TestBackfillRoutedPaymentDoctype(FrappeTestCase):
    def _untyped_request(self, payment_name):
        """A Salis Payment Request carrying an untyped payment link, exactly the shape
        of a row written before ``linked_payment_doctype`` existed."""
        pr = frappe.get_doc(
            {"doctype": SOURCE_DOCTYPE, "expense_type": "Fuel", "amount": 10, "status": "Draft"}
        )
        pr.insert(ignore_permissions=True)
        frappe.db.set_value(
            SOURCE_DOCTYPE,
            pr.name,
            {LINK_NAME_FIELD: payment_name, LINK_DOCTYPE_FIELD: None},
            update_modified=False,
        )
        return pr.name

    def test_types_a_resolvable_link_and_refuses_to_guess_an_unresolvable_one(self):
        # Note becomes a candidate by being the configured target, which also proves
        # the patch reads the router's config rather than a hard-coded list.
        frappe.db.set_single_value(ROUTER, "target_payment_doctype", "Note")
        note = frappe.get_doc(
            {"doctype": "Note", "title": f"Apex A278 {frappe.generate_hash(length=14)}"}
        ).insert(ignore_permissions=True)

        resolvable = self._untyped_request(note.name)
        orphan = f"APEX-A278-ABSENT-{frappe.generate_hash(length=14)}"
        unresolvable = self._untyped_request(orphan)

        # frappe.db.commit is suppressed so the fixtures stay inside the test's
        # transaction; the commit is not the behaviour under test, the typing is.
        with patch.object(frappe.db, "commit"), patch("frappe.log_error") as logged:
            execute()

        self.assertEqual(
            frappe.db.get_value(SOURCE_DOCTYPE, resolvable, LINK_DOCTYPE_FIELD), "Note"
        )
        # Fail closed: no candidate matched, so the type is left blank ...
        self.assertFalse(frappe.db.get_value(SOURCE_DOCTYPE, unresolvable, LINK_DOCTYPE_FIELD))
        # ... and surfaced, so it is a visible gap rather than a silent one.
        self.assertTrue(logged.called)
        self.assertIn(orphan, logged.call_args.kwargs["message"])

    def test_already_typed_rows_are_left_alone(self):
        """Idempotence: a second migrate must not re-decide a row that already has a
        type, or a hand-corrected row would be overwritten by the guess it replaced."""
        frappe.db.set_single_value(ROUTER, "target_payment_doctype", "Note")
        note = frappe.get_doc(
            {"doctype": "Note", "title": f"Apex A278 {frappe.generate_hash(length=14)}"}
        ).insert(ignore_permissions=True)
        request = self._untyped_request(note.name)
        frappe.db.set_value(
            SOURCE_DOCTYPE, request, LINK_DOCTYPE_FIELD, "Payment Entry", update_modified=False
        )

        with patch.object(frappe.db, "commit"), patch("frappe.log_error"):
            execute()

        self.assertEqual(
            frappe.db.get_value(SOURCE_DOCTYPE, request, LINK_DOCTYPE_FIELD), "Payment Entry"
        )
