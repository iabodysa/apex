# Copyright (c) 2026, afmcoltd
"""``terms_signature`` and ``terms_accepted_on`` are the resident's written consent
to the housing terms, written ONCE at check-in by ``front_desk.check_in``'s
``insert()`` (apex/habitat/api/front_desk.py:745-746) and by nothing else. Both
carried ``allow_on_submit: 1``, which opened a plain ``save()`` edit on a submitted
assignment — a path that could replace a signature after the fact. Removing the flag
closes it; this proves the framework itself refuses the edit
(``_validate_update_after_submit``, frappe/model/base_document.py:1050-1083).
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestTermsConsentIsSubmitLocked(FrappeTestCase):
    def _submitted_assignment(self):
        """The fixture assignment itself, submitted: this module never inserts one,
        because Housing Assignment refuses a second active assignment per employee and
        the fixture already holds the only one."""
        name = frappe.db.get_value(
            "Housing Assignment",
            {
                "docstatus": 1,
                "room": ("is", "set"),
                "bed": ("is", "set"),
                "project": ("is", "set"),
            },
            "name",
            order_by="creation asc",
        )
        if not name:
            doc = frappe.get_doc(frappe.get_test_records("Housing Assignment")[0])
            doc.insert()
            doc.submit()
            name = doc.name
        return frappe.get_doc("Housing Assignment", name)

    def test_the_signature_cannot_be_replaced_after_submit(self):
        doc = self._submitted_assignment()
        doc.terms_signature = "data:image/png;base64,AAAA"
        with self.assertRaises(frappe.UpdateAfterSubmitError):
            doc.save()

    def test_the_acceptance_stamp_cannot_be_moved_after_submit(self):
        doc = self._submitted_assignment()
        doc.terms_accepted_on = "2026-01-01 00:00:00"
        with self.assertRaises(frappe.UpdateAfterSubmitError):
            doc.save()
