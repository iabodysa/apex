# Copyright (c) 2026, AFMCO and contributors
"""confirm_handover concurrency + idempotency hardening.

confirm_handover now takes a FOR UPDATE lock on the handover row and re-reads
status / OTP state under that lock, and the receive leg is guarded by
_receive_leg_posted (the positive row landing in to_building) so it posts exactly
once. These tests pin the invariants that lock buys:

- Two correct-OTP confirms (the realistic outcome of two serialized callers: the
  second wins the lock AFTER the first commits, sees Confirmed, returns) post the
  receive leg into the destination store ONCE — never double stock.
- _receive_leg_posted distinguishes the receive leg from the ship leg (which
  shares the voucher_no), so the idempotency guard can't be fooled by the ship
  rows that already exist.
- A direct re-entry into _post_receive_and_confirm posts nothing further.
- Wrong guesses lock out at exactly MAX_OTP_ATTEMPTS. The count does NOT live on the
  document: ``otp_attempts`` would be written and rolled back by the same request that
  reports the miss (``apex_core/utils/otp_lockout.py``), so the counter is a Redis
  window keyed on the document, and the lockout is asserted through ``is_locked_out``.
"""

import frappe
from frappe.utils import flt, today

from apex.apex_core.utils.otp_lockout import is_locked_out
from apex.habitat.api.custody_handover import (
    MAX_OTP_ATTEMPTS,
    _post_receive_and_confirm,
    _receive_leg_posted,
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


class TestConfirmHandoverRace(ApexHabitatTestCase):
    def setUp(self):
        frappe.db.set_single_value("Habitat Settings", "require_handover_otp", 1)
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) \
            or frappe.db.get_value("Cost Center", {"is_group": 0})
        self.site = frappe.get_doc({
            "doctype": "Site", "site_name": _h(12)}).insert(ignore_permissions=True)
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
        self.proc_user = self._user("Accommodation Manager")
        self.recv_user = self._user("Accommodation Manager")

    def _user(self, *roles):
        email = f"chr-{_h(12).lower()}@example.com"
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": "U " + _h(),
                            "send_welcome_email": 0})
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
        return email

    def _approved_handover(self, qty=5):
        """A submitted, verified, Approved handover ready for OTP confirm; returns
        (doc, plaintext_code)."""
        # today(), not a fixed date: the receive leg posts as the receiving supervisor,
        # and Apex Stock Settings allows that role no backdating window at all
        # (apex_core/doctype/apex_stock_settings/apex_stock_settings.py:88-97).
        h = frappe.get_doc({
            "doctype": "Custody Handover", "naming_series": "ACC-HND-.YYYY.-.#####",
            "handover_date": today(), "from_building": self.intake, "to_building": self.dest,
            "procurement_supervisor": self.proc_user, "receiving_supervisor": self.recv_user})
        h.append("items", {"item_type": "Custody Article", "item": self.article, "qty": qty})
        h.insert(ignore_permissions=True)
        h.submit()
        code = frappe.response.get("handover_otp")
        h.db_set("all_items_verified", 1)
        h.db_set("status", "Under Review")
        frappe.set_user(self.recv_user)
        try:
            approve_handover(h.name)
        finally:
            frappe.set_user("Administrator")
        h.reload()
        return h, code

    def test_two_correct_confirms_post_receive_leg_once(self):
        make_goods_receipt(self.intake, self.article, self.proc_user, 5)
        handover, code = self._approved_handover(5)
        self.assertEqual(_store_bal(self.article, self.dest), 0.0)

        frappe.set_user(self.recv_user)
        try:
            confirm_handover(handover.name, code)
            confirm_handover(handover.name, code)
        finally:
            frappe.set_user("Administrator")

        handover.reload()
        self.assertEqual(handover.status, "Confirmed")
        self.assertEqual(_store_bal(self.article, self.dest), 5.0)
        receive_rows = frappe.get_all(
            "Accommodation Stock Ledger",
            filters={
                "voucher_type": "Custody Handover",
                "voucher_no": handover.name,
                "building": self.dest,
                "signed_qty": [">", 0],
                "is_cancelled": 0,
            },
        )
        self.assertEqual(len(receive_rows), 1, "receive leg must post exactly once")

    def test_receive_leg_guard_ignores_ship_leg(self):
        make_goods_receipt(self.intake, self.article, self.proc_user, 3)
        handover, _code = self._approved_handover(3)
        from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
            has_stock_entries,
        )
        self.assertTrue(
            has_stock_entries("Custody Handover", handover.name),
            "the ship leg already exists under this voucher",
        )
        self.assertFalse(
            _receive_leg_posted(handover),
            "the ship leg must not be mistaken for the receive leg",
        )

    def test_direct_reentry_into_post_is_idempotent(self):
        make_goods_receipt(self.intake, self.article, self.proc_user, 4)
        handover, code = self._approved_handover(4)
        frappe.set_user(self.recv_user)
        try:
            confirm_handover(handover.name, code)
        finally:
            frappe.set_user("Administrator")
        handover.reload()
        _post_receive_and_confirm(handover)
        self.assertTrue(_receive_leg_posted(handover))
        self.assertEqual(_store_bal(self.article, self.dest), 4.0)

    def test_wrong_guesses_lock_out_at_max_attempts(self):
        make_goods_receipt(self.intake, self.article, self.proc_user, 2)
        handover, _code = self._approved_handover(2)
        # The window is a cache key, not a row, so no rollback clears it.
        self.addCleanup(
            frappe.cache.delete_value, f"otp-miss:{handover.doctype}:{handover.name}"
        )
        locked = lambda: is_locked_out(  # noqa: E731 — read once per assertion, not held
            handover.doctype, handover.name, attempts=MAX_OTP_ATTEMPTS
        )
        frappe.set_user(self.recv_user)
        try:
            for n in range(1, MAX_OTP_ATTEMPTS):
                with self.assertRaises(frappe.ValidationError):
                    confirm_handover(handover.name, "000000")
                self.assertFalse(locked(), f"locked out after only {n} misses")

            # The miss that carries the count to the limit still reports the wrong code;
            # it is the NEXT attempt the lockout gate refuses, before any comparison.
            with self.assertRaises(frappe.ValidationError):
                confirm_handover(handover.name, "000000")
            self.assertTrue(locked(), "the lockout was never reached")

            with self.assertRaises(frappe.RateLimitExceededError):
                confirm_handover(handover.name, "000000")
        finally:
            frappe.set_user("Administrator")

        self.assertEqual(_store_bal(self.article, self.dest), 0.0)
        self.assertFalse(_receive_leg_posted(handover))
