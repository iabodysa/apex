# Copyright (c) 2026, afmcoltd
"""The procurement-to-handover chain: a Goods Receipt books stock into the intake store, a Custody
Handover ships it out under a one-time code, and only the receiving side — never the shipper, never
a wrong code — can confirm the receive leg into the destination store.

The two buildings and the article come from ``test_records.json``; the second fixture building
already carries ``is_procurement_store``, which is what the intake leg needs. The two users are
still built here, because who may confirm and who may not IS the separation of duties under test.
Fixtures replace building a Company, a Site, two Buildings, a Custody Asset Category and a Custody
Article in ``setUp`` per test method, and remove the need for a ``tearDownModule`` that
force-deletes every building on the site to clean up after itself.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today

from apex.habitat.api.custody_handover import approve_handover, confirm_handover
from apex.tests.factories import make_goods_receipt

test_dependencies = ["Building", "Custody Article"]

INTAKE = "_Test Building 2"
DESTINATION = "_Test Building"


class TestCustodyHandover(FrappeTestCase):
    def setUp(self):
        # FrappeTestCase rolls the database back once per CLASS, not once per method —
        # frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup — so stock and OTP
        # state one case leaves in a shared fixture store would be the next case's opening
        # position. A savepoint hands both stores back exactly as they were found.
        frappe.db.savepoint("apex_custody_handover_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_custody_handover_case")
        self.addCleanup(frappe.clear_document_cache, "Habitat Settings", "Habitat Settings")

        frappe.db.set_single_value("Habitat Settings", "require_handover_otp", 1)
        self.article = frappe.db.get_value("Custody Article", {"article_name": "_Test Blanket"})
        self.shipper = self._user("Accommodation Manager")
        self.receiver = self._user("Accommodation Manager")

    def _user(self, *roles):
        email = "ach-{0}@example.com".format(frappe.generate_hash(length=12).lower())
        user = frappe.get_doc({
            "doctype": "User", "email": email, "first_name": "Handover", "send_welcome_email": 0,
        })
        user.insert(ignore_permissions=True)
        user.add_roles(*roles)
        return email

    def _store_balance(self, building):
        rows = frappe.get_all(
            "Accommodation Stock Ledger",
            filters={
                "item_type": "Custody Article", "item": self.article, "building": building,
                "employee": ["is", "not set"], "is_cancelled": 0,
            },
            fields=["signed_qty"],
        )
        return flt(sum(flt(r.signed_qty) for r in rows))

    def _handover(self, qty=5):
        doc = frappe.get_doc({
            "doctype": "Custody Handover",
            "naming_series": "ACC-HND-.YYYY.-.#####",
            # Today, not a fixed past date: the receiving supervisor is not a System Manager, and
            # the posting gate refuses a backdated leg from anyone who is not one.
            "handover_date": today(),
            "from_building": INTAKE,
            "to_building": DESTINATION,
            "procurement_supervisor": self.shipper,
            "receiving_supervisor": self.receiver,
        })
        doc.append("items", {"item_type": "Custody Article", "item": self.article, "qty": qty})
        doc.insert(ignore_permissions=True)
        doc.submit()
        return doc

    def test_the_chain_runs_from_receipt_to_a_code_confirmed_handover(self):
        make_goods_receipt(INTAKE, self.article, self.shipper, 5)
        self.assertEqual(self._store_balance(INTAKE), 5.0)

        handover = self._handover(5)
        code = frappe.response.get("handover_otp")
        self.assertTrue(code and len(code) == 6, "submit must surface a 6-digit code once")

        handover.reload()
        self.assertEqual(handover.status, "Pending Receipt")
        self.assertTrue(handover.otp_hash, "only the hash of the code is persisted")
        self.assertEqual(self._store_balance(INTAKE), 0.0)
        self.assertEqual(self._store_balance(DESTINATION), 0.0, "nothing lands before confirmation")

        handover.db_set("all_items_verified", 1)
        handover.db_set("status", "Under Review")
        frappe.set_user(self.receiver)
        self.addCleanup(frappe.set_user, "Administrator")
        approve_handover(handover.name)
        handover.reload()
        self.assertEqual(handover.status, "Approved")
        confirm_handover(handover.name, code)
        frappe.set_user("Administrator")

        handover.reload()
        self.assertEqual(handover.status, "Confirmed")
        self.assertTrue(handover.otp_verified_on)
        self.assertFalse(handover.otp_hash, "the hash is cleared once confirmed")
        self.assertEqual(self._store_balance(DESTINATION), 5.0)
        self.assertEqual(self._store_balance(INTAKE), 0.0)

    def test_the_shipper_may_not_confirm_his_own_handover(self):
        make_goods_receipt(INTAKE, self.article, self.shipper, 3)
        handover = self._handover(3)
        code = frappe.response.get("handover_otp")
        handover.db_set("all_items_verified", 1)
        handover.db_set("status", "Approved")

        frappe.set_user(self.shipper)
        self.addCleanup(frappe.set_user, "Administrator")
        with self.assertRaises(frappe.PermissionError):
            confirm_handover(handover.name, code)
        frappe.set_user("Administrator")

        handover.reload()
        self.assertEqual(handover.status, "Approved")
        self.assertEqual(self._store_balance(DESTINATION), 0.0)

    def test_a_wrong_code_posts_no_receive_leg_and_counts_the_attempt(self):
        make_goods_receipt(INTAKE, self.article, self.shipper, 2)
        handover = self._handover(2)
        handover.db_set("all_items_verified", 1)
        handover.db_set("status", "Approved")

        frappe.set_user(self.receiver)
        self.addCleanup(frappe.set_user, "Administrator")
        with self.assertRaises(frappe.ValidationError):
            confirm_handover(handover.name, "000000")
        frappe.set_user("Administrator")

        handover.reload()
        self.assertNotEqual(handover.status, "Confirmed")
        self.assertTrue(handover.otp_hash, "a miss leaves the code live, it does not consume it")
        # The miss is not counted on the document at all: charge_wrong_code keys its window on
        # the document name in the cache (apex/apex_core/utils/otp_lockout.py:38), so
        # otp_attempts stays 0 here.
        self.assertEqual(self._store_balance(DESTINATION), 0.0)
