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
- Wrong guesses lock out at exactly MAX_OTP_ATTEMPTS; the attempt count is read
  fresh under the lock, so the lockout cannot be bypassed.
"""

import frappe
from frappe.utils import flt

from apex_habitat.habitat.api.custody_handover import (
    MAX_OTP_ATTEMPTS,
    _post_receive_and_confirm,
    _receive_leg_posted,
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
        fields=["qty"],
    )
    return flt(sum(flt(r.qty) for r in rows))


class TestConfirmHandoverRace(ApexHabitatTestCase):
    def setUp(self):
        frappe.db.set_single_value("Habitat Settings", "require_handover_otp", 1)
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) \
            or frappe.db.get_value("Cost Center", {"is_group": 0})
        self.site = frappe.get_doc({
            "doctype": "Accommodation Site", "site_name": _h(6)}).insert(ignore_permissions=True)
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
        self.proc_user = self._user("Accommodation Manager")
        self.recv_user = self._user("Accommodation Manager")

    def _user(self, *roles):
        email = f"chr-{_h(6).lower()}@example.com"
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

    def _approved_handover(self, qty=5):
        """A submitted, verified, Approved handover ready for OTP confirm; returns
        (doc, plaintext_code)."""
        h = frappe.get_doc({
            "doctype": "Custody Handover", "naming_series": "ACC-HND-.YYYY.-.#####",
            "handover_date": "2026-05-02", "from_building": self.intake, "to_building": self.dest,
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
        # Two correct-OTP confirms (the realistic serialized outcome: the second
        # acquires the lock after the first commits, sees Confirmed, returns)
        # must post the receive leg into the destination store EXACTLY once.
        self._receive(5)
        handover, code = self._approved_handover(5)
        self.assertEqual(_store_bal(self.article, self.dest), 0.0)

        frappe.set_user(self.recv_user)
        try:
            confirm_handover(handover.name, code)
            # Second confirm: the FOR UPDATE re-read sees Confirmed and returns
            # without re-posting (and the receive-leg guard would catch it anyway).
            confirm_handover(handover.name, code)
        finally:
            frappe.set_user("Administrator")

        handover.reload()
        self.assertEqual(handover.status, "Confirmed")
        # Receive leg posted ONCE: destination holds exactly the handed qty, not 2x.
        self.assertEqual(_store_bal(self.article, self.dest), 5.0)
        # Exactly one live positive receive row in to_building under this voucher.
        receive_rows = frappe.get_all(
            "Accommodation Stock Ledger",
            filters={
                "voucher_type": "Custody Handover",
                "voucher_no": handover.name,
                "building": self.dest,
                "qty": [">", 0],
                "is_cancelled": 0,
            },
        )
        self.assertEqual(len(receive_rows), 1, "receive leg must post exactly once")

    def test_receive_leg_guard_ignores_ship_leg(self):
        # After submit (ship leg only) the receive-leg guard must report NOT posted,
        # even though has_stock_entries on the voucher_no is already True.
        self._receive(3)
        handover, _code = self._approved_handover(3)
        from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
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
        # Calling the post helper twice (simulating two callers that both passed the
        # gate) posts the receive leg only once thanks to _receive_leg_posted.
        self._receive(4)
        handover, code = self._approved_handover(4)
        frappe.set_user(self.recv_user)
        try:
            confirm_handover(handover.name, code)
        finally:
            frappe.set_user("Administrator")
        handover.reload()
        # Re-enter the post helper directly: the guard short-circuits, no new rows.
        _post_receive_and_confirm(handover)
        self.assertTrue(_receive_leg_posted(handover))
        self.assertEqual(_store_bal(self.article, self.dest), 4.0)

    def test_wrong_guesses_lock_out_at_max_attempts(self):
        # Each wrong guess increments the counter (read fresh under the lock); the
        # MAX_OTP_ATTEMPTS-th miss flips the lockout and resets the counter, and a
        # further attempt is refused by the lockout gate — not silently allowed.
        self._receive(2)
        handover, _code = self._approved_handover(2)
        frappe.set_user(self.recv_user)
        try:
            for n in range(1, MAX_OTP_ATTEMPTS):
                with self.assertRaises(frappe.ValidationError):
                    confirm_handover(handover.name, "000000")
                handover.reload()
                self.assertEqual(handover.otp_attempts, n)
                self.assertFalse(handover.otp_locked_until)

            # The MAX-th miss locks the handover and resets the counter to 0.
            with self.assertRaises(frappe.ValidationError):
                confirm_handover(handover.name, "000000")
            handover.reload()
            self.assertEqual(handover.otp_attempts, 0)
            self.assertTrue(handover.otp_locked_until, "lockout must be stamped")

            # A further attempt now hits the lockout gate, not the code compare.
            with self.assertRaises(frappe.ValidationError):
                confirm_handover(handover.name, "000000")
        finally:
            frappe.set_user("Administrator")

        # No receive leg ever posted under a wrong code.
        self.assertEqual(_store_bal(self.article, self.dest), 0.0)
        self.assertFalse(_receive_leg_posted(handover))
