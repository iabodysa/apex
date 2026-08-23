# Copyright (c) 2026, afmcoltd
"""``is_assigned``/``assigned_to_trip`` carried ``allow_on_submit: 1`` while every
writer in the app (``apex.salis.utils.drive_transport_request`` and
``revert_transport_request``) reaches them only through ``frappe.db.set_value`` —
a write path that needs no framework permission at all. Removing the flag lets
the framework refuse a plain ``save()`` edit to them again. Proven through
``insert()``/``submit()``/``save()``, never by calling a controller method
directly.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestTransportRequestIsAssignedIsFrozenAfterSubmit(FrappeTestCase):
    def _submitted_request(self):
        doc = frappe.new_doc("Transport Request")
        doc.service_line = "Administrative Trip"
        doc.request_type = "Administrative Trip / Document Signing"
        doc.destination = "Riyadh Head Office"
        doc.requested_by = "Administrator"
        doc.insert()
        doc.submit()
        return doc

    def test_editing_is_assigned_after_submit_is_refused(self):
        doc = self._submitted_request()
        doc.is_assigned = 1
        self.assertRaises(frappe.exceptions.UpdateAfterSubmitError, doc.save)
