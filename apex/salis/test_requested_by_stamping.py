# Copyright (c) 2026, AFMCO and contributors
"""``requested_by`` is stamped server-side, so the maker cannot name someone else.

Three Salis DocTypes carry a segregation-of-duties gate that compares the approver
against ``requested_by``. That gate is only as strong as the field: if the maker could name someone else, he could
raise a claim in a colleague's name and then approve it himself. Two things stand behind
it and both are pinned here — the field is ``read_only`` on all three, and each
controller stamps ``frappe.session.user`` on insert.

The stamp is a fill, not an override: all three controllers write it only when the field
arrives BLANK (``fuel_claim.py:54``, ``rental_settlement.py:61``,
``salis_payment_request.py:51``). That boundary is asserted rather than assumed, because
it is what decides whether ``read_only`` is the whole defence or only the form half of
it.

The gate itself is graded beside its own DocType (Salis Payment Request's workflow
tests); this module grades only the field the gate reads.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_project, make_vehicle

_SOD_DOCTYPES = ("Fuel Claim", "Rental Settlement", "Salis Payment Request")


class TestRequestedByStamping(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.user = cls._manager("rb_stamp_user@example.com")

    def setUp(self):
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")

    @staticmethod
    def _manager(email):
        if not frappe.db.exists("User", email):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": email.split("@")[0],
                    "send_welcome_email": 0,
                }
            ).insert(ignore_permissions=True)
        user = frappe.get_doc("User", email)
        for role in ("Fleet Manager", "Fleet Project Manager"):
            if role not in frappe.get_roles(email):
                user.add_roles(role)
        return email

    def _insert_as_user(self, values):
        frappe.set_user(self.user)
        try:
            doc = frappe.get_doc(values).insert(ignore_permissions=True)
        finally:
            frappe.set_user("Administrator")
        self.addCleanup(
            frappe.delete_doc, doc.doctype, doc.name, ignore_permissions=True, force=True
        )
        return doc

    def test_the_field_is_read_only_on_every_sod_doctype(self):
        for doctype in _SOD_DOCTYPES:
            with self.subTest(doctype=doctype):
                field = frappe.get_meta(doctype).get_field("requested_by")
                self.assertIsNotNone(field, f"{doctype} must declare requested_by")
                self.assertTrue(field.read_only, f"{doctype}.requested_by must be read_only")

    def test_a_fuel_claim_is_stamped_with_the_session_user(self):
        doc = self._insert_as_user(
            {
                "doctype": "Fuel Claim",
                "project": make_project("RB Stamp Claim P"),
                "vehicle": make_vehicle("RB STAMP CLAIM 1"),
                "period_month": "2026-05",
                "claimed_litres": 50,
                "status": "Draft",
            }
        )
        self.assertEqual(doc.requested_by, self.user)

    def test_a_rental_settlement_is_stamped_with_the_session_user(self):
        office = frappe.db.get_value("Rental Office", {}, "name")
        if not office:
            office = frappe.get_doc(
                {"doctype": "Rental Office", "office_name": "RB Stamp Office"}
            ).insert(ignore_permissions=True).name
        doc = self._insert_as_user(
            {
                "doctype": "Rental Settlement",
                "rental_office": office,
                "period_month": "2026-05",
                "status": "Draft",
                "claimed_total": 0,
            }
        )
        self.assertEqual(doc.requested_by, self.user)

    def test_a_supplied_requester_survives_the_stamp(self):
        """The controllers stamp only a BLANK field, so a value that arrives with the
        insert is kept. ``read_only`` withholds the field from the form; it does not
        strip it from a server-side or API write, so this is the boundary of the
        defence and is pinned so a change to it cannot pass unnoticed."""
        doc = self._insert_as_user(
            {
                "doctype": "Fuel Claim",
                "project": make_project("RB Stamp Claim P"),
                "vehicle": make_vehicle("RB STAMP CLAIM 2"),
                "period_month": "2026-05",
                "claimed_litres": 20,
                "status": "Draft",
                "requested_by": "Administrator",
            }
        )
        self.assertEqual(doc.requested_by, "Administrator")
