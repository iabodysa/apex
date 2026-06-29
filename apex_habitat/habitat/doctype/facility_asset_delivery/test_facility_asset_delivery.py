# Copyright (c) 2026, AFMCO and contributors
"""Facility Asset Delivery (T-673): the 3-exit transfer lock + on-site code receipt.

Asserts the lock cannot be released until ALL THREE exits pass (and that exits
must pass IN ORDER), that the on-site code confirm actually moves the tracked
asset into the destination only after Released, and that separation of duties and
a wrong code both block the move."""

import frappe

from apex_habitat.habitat.api.facility_asset_delivery import (
    confirm_receipt,
    pass_exit_1,
    pass_exit_2,
    pass_exit_3,
)
from apex_habitat.tests.test_utils import ApexHabitatTestCase


def _h(n=4):
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
            {"doctype": "Accommodation Site", "site_name": _h(6)}
        ).insert(ignore_permissions=True)
        self.intake = frappe.get_doc(
            {
                "doctype": "Accommodation Building",
                "building_name": "Intake " + _h(),
                "site": self.site.name,
                "company": self.company,
                "is_procurement_store": 1,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        self.dest = frappe.get_doc(
            {
                "doctype": "Accommodation Building",
                "building_name": "Dest " + _h(),
                "site": self.site.name,
                "company": self.company,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        # The asset starts in the intake store; a delivery moves it to dest.
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
        # Distinct users so SoD (initiator != receiver) and per-exit roles hold.
        self.initiator = self._user("Procurement Supervisor")
        self.receiver = self._user("Accommodation Manager", "Resident Supervisor")

    def _user(self, *roles):
        email = f"fad-{_h(6).lower()}@example.com"
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

    # --- the 3-exit transfer lock ---------------------------------------------

    def test_submit_opens_pending_exits_and_issues_code(self):
        d = self._delivery()
        self.assertEqual(d.status, "Pending Exits")
        code = frappe.response.get("delivery_otp")
        self.assertTrue(code and len(code) == 6, "submit must surface a 6-digit code once")
        # Asset has NOT moved yet — still in the intake store.
        self.assertEqual(frappe.db.get_value("Facility Asset", self.asset, "building"), self.intake)

    def test_lock_not_released_until_all_three_exits_pass(self):
        d = self._delivery()
        frappe.set_user("Administrator")  # admin override clears every exit
        try:
            pass_exit_1(d.name)
            d.reload()
            self.assertEqual(d.status, "Pending Exits")
            self.assertTrue(d.exit1_security_cleared)

            pass_exit_2(d.name)
            d.reload()
            self.assertEqual(d.status, "Pending Exits")
            self.assertTrue(d.exit2_logistics_cleared)

            # The third exit opens the lock and issues the on-site code.
            pass_exit_3(d.name)
        finally:
            frappe.set_user("Administrator")
        d.reload()
        self.assertEqual(d.status, "Released")
        self.assertTrue(d.exit3_receiving_cleared)
        self.assertTrue(frappe.response.get("delivery_otp"))
        # Still NOT moved — release only opens the on-site receipt step.
        self.assertEqual(frappe.db.get_value("Facility Asset", self.asset, "building"), self.intake)

    def test_exits_must_pass_in_order(self):
        d = self._delivery()
        frappe.set_user("Administrator")
        try:
            # Skipping exit 1 -> exit 2 is rejected.
            with self.assertRaises(frappe.ValidationError):
                pass_exit_2(d.name)
            # Skipping straight to exit 3 is rejected.
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
        # Only exits 1+2 passed — lock is still closed.
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

    # --- the on-site code receipt ---------------------------------------------

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
        # The asset has now moved into the destination accommodation.
        self.assertEqual(frappe.db.get_value("Facility Asset", self.asset, "building"), self.dest)
        self.assertEqual(
            frappe.db.get_value("Facility Asset", self.asset, "previous_building"), self.intake
        )
        # An immutable movement-ledger row records the from->to.
        rows = frappe.get_all(
            "Facility Asset Movement Ledger",
            filters={"source_doctype": "Facility Asset Delivery", "source_name": d.name},
        )
        self.assertEqual(len(rows), 1)

    def test_initiator_cannot_confirm_own_delivery(self):
        d = self._delivery()
        code = self._release(d)
        # Separation of duties: the initiator who shipped may not confirm receipt.
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
