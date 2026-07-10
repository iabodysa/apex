# Copyright (c) 2026, AFMCO and contributors
"""Procurement -> OTP-confirmed handover chain: a Goods Receipt books stock INTO a
procurement intake store; a Custody Handover ships it out (OTP issued) and, after
the receiving side verifies + approves, the OTP confirm posts the receive leg into
the destination store. Asserts the store-balance flow on the Accommodation Stock
Ledger and the OTP/separation-of-duties gates."""

import frappe
from frappe.utils import flt

from apex_habitat.habitat.api.custody_handover import (
    approve_handover,
    confirm_handover,
)
from apex_habitat.tests.test_utils import ApexHabitatTestCase


def _h(n=4):
    return frappe.generate_hash(length=n).upper()


def _store_bal(article, building):
    """Unassigned (employee unset) store balance of an article in a building."""
    rows = frappe.get_all(
        "Accommodation Stock Ledger",
        filters={
            "item_type": "Custody Article",
            "item": article,
            "building": building,
            "employee": ["is", "not set"],
            "is_cancelled": 0,
        },
        fields=["signed_qty"],
    )
    return flt(sum(flt(r.signed_qty) for r in rows))


class TestCustodyHandover(ApexHabitatTestCase):
    def setUp(self):
        # The OTP gate is off by default (a Check with no default reads 0 on the
        # Single); turn it on so the confirm path actually exercises the code/expiry.
        frappe.db.set_single_value("Habitat Settings", "require_handover_otp", 1)
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) \
            or frappe.db.get_value("Cost Center", {"is_group": 0})
        self.site = frappe.get_doc({
            "doctype": "Accommodation Site", "site_name": _h(6)}).insert(ignore_permissions=True)
        # Source = a procurement intake store; destination = a receiving building store.
        self.intake = frappe.get_doc({
            "doctype": "Accommodation Building", "building_name": "Intake " + _h(),
            "site": self.site.name, "total_capacity": 4, "company": self.company,
            "default_cost_center": cc, "is_procurement_store": 1}).insert(ignore_permissions=True).name
        self.dest = frappe.get_doc({
            "doctype": "Accommodation Building", "building_name": "Dest " + _h(),
            "site": self.site.name, "total_capacity": 4, "company": self.company,
            "default_cost_center": cc}).insert(ignore_permissions=True).name
        cat = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc({
            "doctype": "Custody Asset Category", "category_name": "Cat " + _h()}).insert(ignore_permissions=True).name
        self.article = frappe.get_doc({
            "doctype": "Custody Article", "naming_series": "ART-.####",
            "article_name": "Item " + _h(), "category": cat,
            "unit_of_measure": "Nos"}).insert(ignore_permissions=True).name
        # Two distinct users so separation of duties (shipper != confirmer) holds.
        self.proc_user = self._user("Accommodation Manager")
        self.recv_user = self._user("Accommodation Manager")

    def _user(self, *roles):
        email = f"ach-{_h(6).lower()}@example.com"
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": "U " + _h(),
                            "send_welcome_email": 0})
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
        return email

    def _receive(self, qty=5):
        gr = frappe.get_doc({
            "doctype": "Goods Receipt", "naming_series": "ACC-GRN-.YYYY.-.#####",
            "receipt_date": "2026-05-01", "intake_building": self.intake,
            "procurement_supervisor": self.proc_user})
        gr.append("items", {"item_type": "Custody Article", "item": self.article, "qty": qty})
        gr.insert(ignore_permissions=True)
        gr.submit()
        return gr

    def _handover(self, qty=5):
        h = frappe.get_doc({
            "doctype": "Custody Handover", "naming_series": "ACC-HND-.YYYY.-.#####",
            "handover_date": "2026-05-02", "from_building": self.intake, "to_building": self.dest,
            "procurement_supervisor": self.proc_user, "receiving_supervisor": self.recv_user})
        h.append("items", {"item_type": "Custody Article", "item": self.article, "qty": qty})
        h.insert(ignore_permissions=True)
        h.submit()
        return h

    def test_full_chain_receipt_to_otp_confirmed_handover(self):
        # 1) Goods Receipt books stock into the intake store.
        self._receive(5)
        self.assertEqual(_store_bal(self.article, self.intake), 5.0)

        # 2) Handover submit ships the goods out of the intake store and issues an OTP.
        handover = self._handover(5)
        code = frappe.response.get("handover_otp")
        self.assertTrue(code and len(code) == 6, "submit must surface a 6-digit OTP once")
        handover.reload()
        self.assertEqual(handover.status, "Pending Receipt")
        self.assertTrue(handover.otp_hash, "only the OTP hash is persisted")
        # Ship leg has left the source store; nothing in the destination yet.
        self.assertEqual(_store_bal(self.article, self.intake), 0.0)
        self.assertEqual(_store_bal(self.article, self.dest), 0.0)

        # 3) Receiving side verifies every line, moves Under Review, and approves.
        handover.db_set("all_items_verified", 1)
        handover.db_set("status", "Under Review")
        frappe.set_user(self.recv_user)
        try:
            approve_handover(handover.name)
            handover.reload()
            self.assertEqual(handover.status, "Approved")

            # 4) OTP confirm posts the receive leg into the destination store.
            confirm_handover(handover.name, code)
        finally:
            frappe.set_user("Administrator")
        handover.reload()
        self.assertEqual(handover.status, "Confirmed")
        self.assertTrue(handover.otp_verified_on)
        self.assertFalse(handover.otp_hash, "hash is cleared once confirmed")
        # Custody now sits in the destination store; the intake store stays empty.
        self.assertEqual(_store_bal(self.article, self.dest), 5.0)
        self.assertEqual(_store_bal(self.article, self.intake), 0.0)

    def test_shipper_cannot_confirm_own_handover(self):
        self._receive(3)
        handover = self._handover(3)
        code = frappe.response.get("handover_otp")
        handover.db_set("all_items_verified", 1)
        handover.db_set("status", "Approved")
        # Separation of duties: the procurement supervisor who shipped may not confirm.
        frappe.set_user(self.proc_user)
        try:
            with self.assertRaises(frappe.PermissionError):
                confirm_handover(handover.name, code)
        finally:
            frappe.set_user("Administrator")
        handover.reload()
        self.assertEqual(handover.status, "Approved")
        self.assertEqual(_store_bal(self.article, self.dest), 0.0)

    def test_wrong_otp_does_not_post_receive_leg(self):
        self._receive(2)
        handover = self._handover(2)
        handover.db_set("all_items_verified", 1)
        handover.db_set("status", "Approved")
        frappe.set_user(self.recv_user)
        try:
            with self.assertRaises(frappe.ValidationError):
                confirm_handover(handover.name, "000000")
        finally:
            frappe.set_user("Administrator")
        handover.reload()
        self.assertNotEqual(handover.status, "Confirmed")
        self.assertEqual(handover.otp_attempts, 1)
        self.assertEqual(_store_bal(self.article, self.dest), 0.0)


def tearDownModule():
    # P-148: drop this module's committed Accommodation Buildings so the suite's
    # post-run building count returns to the pre-suite baseline (see factories.py).
    from apex_habitat.tests import factories

    factories.purge_test_buildings()
