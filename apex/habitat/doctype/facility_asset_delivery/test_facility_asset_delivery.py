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

    def _deliver(self):
        """A delivery carried all the way to Delivered. Returns the delivery doc."""
        d = self._delivery()
        code = self._release(d)
        frappe.set_user(self.receiver)
        try:
            confirm_receipt(d.name, code)
        finally:
            frappe.set_user("Administrator")
        d.reload()
        self.assertEqual(d.status, "Delivered")
        return d

    def test_cancelling_a_delivery_returns_the_asset_to_the_room_it_left(self):
        """Cancel restored only the building while move_asset_on_delivery writes the
        room too, so the asset landed back in the intake store still reporting the
        destination's room — a location that had never existed."""
        origin_room = "Intake Shelf " + _h(6)
        frappe.db.set_value("Facility Asset", self.asset, "location_in_building", origin_room)

        d = self._deliver()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", self.asset, "location_in_building"),
            d.to_location_in_building,
            "the delivery must have put the asset in the destination room first",
        )

        d.db_set("cancellation_reason", "Delivery reversed in test")
        d.reload()
        d.cancel()

        asset = frappe.db.get_value(
            "Facility Asset",
            self.asset,
            ["building", "location_in_building", "movement_count"],
            as_dict=True,
        )
        self.assertEqual(
            asset.building, self.intake, "cancel must return the asset to the intake store"
        )
        self.assertEqual(
            asset.location_in_building,
            origin_room,
            "cancel must return the asset to the room it left",
        )
        self.assertNotEqual(
            asset.location_in_building,
            d.to_location_in_building,
            "the destination room must not survive the cancel",
        )
        self.assertEqual(asset.movement_count, 0, "cancel must decrement movement_count back to 0")

    _AUDIT_TRAIL = (
        "previous_building",
        "previous_location_in_building",
        "last_movement_date",
    )

    def _audit_trail(self):
        return frappe.db.get_value(
            "Facility Asset", self.asset, list(self._AUDIT_TRAIL), as_dict=True
        )

    def test_cancelling_a_delivery_clears_the_audit_trail_it_stamped(self):
        """move_asset_on_delivery stamps previous_*/last_movement_date and on_cancel
        reset none of them, so a cancelled delivery left the asset back in the intake
        store claiming it had previously been in the intake store, dated to a
        delivery that no longer exists."""
        before = self._audit_trail()
        self.assertFalse(before.previous_building, "seed asset must carry no previous building")
        self.assertFalse(before.last_movement_date, "seed asset must carry no movement date")

        d = self._deliver()
        stamped = self._audit_trail()
        self.assertEqual(
            stamped.previous_building, self.intake, "the delivery must stamp the prior building"
        )
        self.assertTrue(stamped.last_movement_date, "the delivery must stamp the movement date")

        d.db_set("cancellation_reason", "Delivery reversed in test")
        d.reload()
        d.cancel()

        after = self._audit_trail()
        for field in self._AUDIT_TRAIL:
            # NULL and "" both read as blank; compare on that axis, not on identity.
            self.assertEqual(
                after.get(field) or None,
                before.get(field) or None,
                f"cancel must return {field} to its pre-delivery value",
            )
        self.assertNotEqual(
            after.previous_building,
            self.intake,
            "an asset back in the intake store must not also claim it came from there",
        )

    def test_cancelling_a_superseded_delivery_cannot_drag_the_asset_back(self):
        """A Delivered delivery followed by a movement onward: cancelling the delivery
        used to restore from_building blindly, teleporting the asset back into the
        intake store it had physically left."""
        d = self._delivery()
        code = self._release(d)
        frappe.set_user(self.receiver)
        try:
            confirm_receipt(d.name, code)
        finally:
            frappe.set_user("Administrator")
        d.reload()
        self.assertEqual(d.status, "Delivered")

        onward = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "Onward " + _h(),
                "site": self.site.name,
                "company": self.company,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        mv = frappe.get_doc(
            {
                "doctype": "Facility Asset Movement",
                "movement_date": "2026-06-30",
                "facility_asset": self.asset,
                "movement_category": "Same-Company Relocation",
                "from_building": self.dest,
                "to_building": onward,
            }
        ).insert(ignore_permissions=True)
        mv.submit()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", self.asset, "building"),
            onward,
            "the movement must have carried the asset past the delivery destination",
        )

        d.db_set("cancellation_reason", "Out-of-order cancel attempt")
        d.reload()
        with self.assertRaises(frappe.ValidationError) as caught:
            d.cancel()
        # Every framework pre-cancel check subclasses ValidationError too, so a bare
        # assertRaises would pass on a link or timestamp failure instead of the guard.
        self.assertNotIsInstance(
            caught.exception,
            (frappe.LinkValidationError, frappe.TimestampMismatchError),
            "the refusal must come from the ordering guard, not a framework pre-cancel check",
        )

        landed = frappe.db.get_value("Facility Asset", self.asset, "building")
        self.assertEqual(landed, onward, "a superseded delivery cancel must not move the asset")
        self.assertNotEqual(
            landed, self.intake, "the asset must never be dragged back to the intake store"
        )
        self.assertEqual(
            frappe.db.get_value("Facility Asset Delivery", d.name, "docstatus"),
            1,
            "a refused cancel must leave the delivery submitted",
        )

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
