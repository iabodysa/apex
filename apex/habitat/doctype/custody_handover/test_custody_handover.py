# Copyright (c) 2026, AFMCO and contributors
"""Procurement -> OTP-confirmed handover chain: a Goods Receipt books stock INTO a
procurement intake store; a Custody Handover ships it out (OTP issued) and, after
the receiving side verifies + approves, the OTP confirm posts the receive leg into
the destination store. Asserts the store-balance flow on the Accommodation Stock
Ledger and the OTP/separation-of-duties gates."""

import frappe
from frappe.utils import flt

from apex.habitat.api.custody_handover import (
    approve_handover,
    confirm_handover,
)
from apex.tests.factories import ApexHabitatTestCase
from apex.tests.factories import make_goods_receipt


def _h(n=12):
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
        # [#sw0u1v]
        frappe.db.set_single_value("Habitat Settings", "require_handover_otp", 1)
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) \
            or frappe.db.get_value("Cost Center", {"is_group": 0})
        self.site = frappe.get_doc({
            "doctype": "Site", "site_name": _h(12)}).insert(ignore_permissions=True)
        # [#r3sfwe]
        self.intake = frappe.get_doc({
            "doctype": "Building", "building_name": "Intake " + _h(),
            "site": self.site.name, "total_capacity": 4, "company": self.company,
            "default_cost_center": cc, "is_procurement_store": 1}).insert(ignore_permissions=True).name
        self.dest = frappe.get_doc({
            "doctype": "Building", "building_name": "Dest " + _h(),
            "site": self.site.name, "total_capacity": 4, "company": self.company,
            "default_cost_center": cc}).insert(ignore_permissions=True).name
        cat = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc({
            "doctype": "Custody Asset Category", "category_name": "Cat " + _h()}).insert(ignore_permissions=True).name
        self.article = frappe.get_doc({
            "doctype": "Custody Article", "naming_series": "ART-.####",
            "article_name": "Item " + _h(), "category": cat,
            "unit_of_measure": "Nos"}).insert(ignore_permissions=True).name
        # [#ho90u4]
        self.proc_user = self._user("Accommodation Manager")
        self.recv_user = self._user("Accommodation Manager")

    def _user(self, *roles):
        email = f"ach-{_h(12).lower()}@example.com"
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": "U " + _h(),
                            "send_welcome_email": 0})
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
        return email

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
        # [#i04hcl]
        make_goods_receipt(self.intake, self.article, self.proc_user, 5)
        self.assertEqual(_store_bal(self.article, self.intake), 5.0)

        # [#besej4]
        handover = self._handover(5)
        code = frappe.response.get("handover_otp")
        self.assertTrue(code and len(code) == 6, "submit must surface a 6-digit OTP once")
        handover.reload()
        self.assertEqual(handover.status, "Pending Receipt")
        self.assertTrue(handover.otp_hash, "only the OTP hash is persisted")
        # [#k93zah]
        self.assertEqual(_store_bal(self.article, self.intake), 0.0)
        self.assertEqual(_store_bal(self.article, self.dest), 0.0)

        # [#fodi5d]
        handover.db_set("all_items_verified", 1)
        handover.db_set("status", "Under Review")
        frappe.set_user(self.recv_user)
        try:
            approve_handover(handover.name)
            handover.reload()
            self.assertEqual(handover.status, "Approved")

            # [#qguqz2]
            confirm_handover(handover.name, code)
        finally:
            frappe.set_user("Administrator")
        handover.reload()
        self.assertEqual(handover.status, "Confirmed")
        self.assertTrue(handover.otp_verified_on)
        self.assertFalse(handover.otp_hash, "hash is cleared once confirmed")
        # [#r93gdh]
        self.assertEqual(_store_bal(self.article, self.dest), 5.0)
        self.assertEqual(_store_bal(self.article, self.intake), 0.0)

    def test_shipper_cannot_confirm_own_handover(self):
        make_goods_receipt(self.intake, self.article, self.proc_user, 3)
        handover = self._handover(3)
        code = frappe.response.get("handover_otp")
        handover.db_set("all_items_verified", 1)
        handover.db_set("status", "Approved")
        # [#4co2um]
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
        make_goods_receipt(self.intake, self.article, self.proc_user, 2)
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
    # [#2esm3x]
    from apex.tests import factories

    factories.purge_test_buildings()
