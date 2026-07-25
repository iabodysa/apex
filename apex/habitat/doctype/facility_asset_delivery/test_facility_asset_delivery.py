# Copyright (c) 2026, AFMCO and contributors
"""Facility Asset Delivery (T-673): the 3-exit transfer lock + on-site code receipt.

Asserts the lock cannot be released until ALL THREE exits pass (and that exits
must pass IN ORDER), that the on-site code confirm actually moves the tracked
asset into the destination only after Released, and that separation of duties and
a wrong code both block the move."""

import frappe

from apex.habitat.api.facility_asset_delivery import (
    confirm_receipt,
    pass_exit_1,
    pass_exit_2,
    pass_exit_3,
)
from apex.tests.factories import ApexHabitatTestCase


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestFacilityAssetDelivery(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": "Test Co",
                "default_currency": "SAR",
                "country": "Saudi Arabia",
            }
        ).insert(ignore_permissions=True).name
        self.site = frappe.get_doc(
            {"doctype": "Site", "site_name": _h(12)}
        ).insert(ignore_permissions=True)
        self.intake = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "Intake " + _h(),
                "site": self.site.name,
                "company": self.company,
                "is_procurement_store": 1,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        self.dest = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "Dest " + _h(),
                "site": self.site.name,
                "company": self.company,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        # [#nt1itk]
        self.asset = frappe.get_doc(
            {
                "doctype": "Facility Asset",
                "naming_series": "FAC-AST-.YYYY.-.####",
                "asset_name": "Camera " + _h(),
                "asset_category": "CCTV Camera",
                "building": self.intake,
                "responsible_supervisor": "Administrator",
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        # [#cy36us]
        self.initiator = self._user("Procurement Supervisor")
        self.receiver = self._user("Accommodation Manager", "Resident Supervisor")

    def _user(self, *roles):
        email = f"fad-{_h(12).lower()}@example.com"
        u = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "U " + _h(),
                "send_welcome_email": 0,
            }
        )
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
        return email

    def _delivery(self):
        d = frappe.get_doc(
            {
                "doctype": "Facility Asset Delivery",
                "naming_series": "FAD-.YYYY.-.#####",
                "delivery_date": "2026-06-29",
                "facility_asset": self.asset,
                "from_building": self.intake,
                "to_building": self.dest,
                "to_location_in_building": "Server Room",
                "initiated_by": self.initiator,
                "receiving_supervisor": self.receiver,
            }
        )
        d.insert(ignore_permissions=True)
        d.submit()
        return d

    # [#4so00v]

    def test_submit_opens_pending_exits_and_issues_code(self):
        d = self._delivery()
        self.assertEqual(d.status, "Pending Exits")
        code = frappe.response.get("delivery_otp")
        self.assertTrue(code and len(code) == 6, "submit must surface a 6-digit code once")
        # [#ev2tzj]
        self.assertEqual(frappe.db.get_value("Facility Asset", self.asset, "building"), self.intake)

    def test_lock_not_released_until_all_three_exits_pass(self):
        d = self._delivery()
        frappe.set_user("Administrator")  # [#d1vue9]
        try:
            pass_exit_1(d.name)
            d.reload()
            self.assertEqual(d.status, "Pending Exits")
            self.assertTrue(d.exit1_security_cleared)

            pass_exit_2(d.name)
            d.reload()
            self.assertEqual(d.status, "Pending Exits")
            self.assertTrue(d.exit2_logistics_cleared)

            # [#e6al6k]
            pass_exit_3(d.name)
        finally:
            frappe.set_user("Administrator")
        d.reload()
        self.assertEqual(d.status, "Released")
        self.assertTrue(d.exit3_receiving_cleared)
        self.assertTrue(frappe.response.get("delivery_otp"))
        # [#b6uv64]
        self.assertEqual(frappe.db.get_value("Facility Asset", self.asset, "building"), self.intake)

    def test_exits_must_pass_in_order(self):
        d = self._delivery()
        frappe.set_user("Administrator")
        try:
            # [#i7qoaj]
            with self.assertRaises(frappe.ValidationError):
                pass_exit_2(d.name)
            # [#p6efup]
            with self.assertRaises(frappe.ValidationError):
                pass_exit_3(d.name)
        finally:
            frappe.set_user("Administrator")
        d.reload()
        self.assertEqual(d.status, "Pending Exits")
        self.assertFalse(d.exit2_logistics_cleared)
        self.assertFalse(d.exit3_receiving_cleared)

    def test_cannot_confirm_before_release(self):
        d = self._delivery()
        code = frappe.response.get("delivery_otp")
        # [#q0dk97]
        frappe.set_user("Administrator")
        try:
            pass_exit_1(d.name)
            pass_exit_2(d.name)
        finally:
            frappe.set_user("Administrator")
        frappe.set_user(self.receiver)
        try:
            with self.assertRaises(frappe.ValidationError):
                confirm_receipt(d.name, code or "000000")
        finally:
            frappe.set_user("Administrator")
        d.reload()
        self.assertNotEqual(d.status, "Delivered")
        self.assertEqual(frappe.db.get_value("Facility Asset", self.asset, "building"), self.intake)

    # [#umj1im]

    def _release(self, d):
        """Pass all three exits (admin) and return the freshly issued code."""
        frappe.set_user("Administrator")
        try:
            pass_exit_1(d.name)
            pass_exit_2(d.name)
            pass_exit_3(d.name)
        finally:
            frappe.set_user("Administrator")
        return frappe.response.get("delivery_otp")

    def test_confirm_moves_asset_into_destination(self):
        d = self._delivery()
        code = self._release(d)
        frappe.set_user(self.receiver)
        try:
            confirm_receipt(d.name, code)
        finally:
            frappe.set_user("Administrator")
        d.reload()
        self.assertEqual(d.status, "Delivered")
        self.assertTrue(d.otp_verified_on)
        self.assertFalse(d.otp_hash, "hash is cleared once delivered")
        # [#bn2jds]
        self.assertEqual(frappe.db.get_value("Facility Asset", self.asset, "building"), self.dest)
        self.assertEqual(
            frappe.db.get_value("Facility Asset", self.asset, "previous_building"), self.intake
        )
        # [#r1j4bo]
        rows = frappe.get_all(
            "Facility Asset Movement Ledger",
            filters={"source_doctype": "Facility Asset Delivery", "source_name": d.name},
        )
        self.assertEqual(len(rows), 1)

    def test_initiator_cannot_confirm_own_delivery(self):
        d = self._delivery()
        code = self._release(d)
        # [#nao53r]
        frappe.set_user(self.initiator)
        try:
            with self.assertRaises(frappe.PermissionError):
                confirm_receipt(d.name, code)
        finally:
            frappe.set_user("Administrator")
        d.reload()
        self.assertEqual(d.status, "Released")
        self.assertEqual(frappe.db.get_value("Facility Asset", self.asset, "building"), self.intake)

    def test_wrong_code_does_not_move_asset(self):
        d = self._delivery()
        self._release(d)
        frappe.set_user(self.receiver)
        try:
            with self.assertRaises(frappe.ValidationError):
                confirm_receipt(d.name, "000000")
        finally:
            frappe.set_user("Administrator")
        d.reload()
        self.assertNotEqual(d.status, "Delivered")
        self.assertEqual(d.otp_attempts, 1)
        self.assertEqual(frappe.db.get_value("Facility Asset", self.asset, "building"), self.intake)


def tearDownModule():
    # [#2esm3x]
    from apex.tests import factories

    factories.purge_test_buildings()
