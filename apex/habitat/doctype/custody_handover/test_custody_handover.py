# Copyright (c) 2026, afmcoltd
"""What Custody Handover guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``validate``,
``on_submit``, and the state machine in ``habitat.api.custody_handover``
(``approve_handover``, ``confirm_handover``, ``reject_handover``), driven through
those real actions rather than a raw status assignment. ``validate`` refuses a
same-building move, a shared supervisor on both sides, and a non-positive quantity.
Submit refuses a source store that cannot cover the quantity, else ships the goods out
and issues a one-time code. The receive leg only posts into the destination store once
the code is confirmed by the receiving side — never the procurement supervisor who
shipped it — and a rejection reverses the ship leg instead of leaving it stranded.

NOTE for the owner: the "Pending Receipt" -> "Under Review" step has no dedicated
Document method or whitelisted action anywhere in the app; the form's own client
script (``custody_handover.js:19``) sets the field directly
(``frm.set_value("status", "Under Review")``) and calls ``frm.save()``. That save
would itself raise ``UpdateAfterSubmitError`` on a real site, because ``status``
carries no ``allow_on_submit`` in ``custody_handover.json`` — a submitted document
refuses any change to a field that is not so flagged. This test reaches "Under
Review" with ``db_set`` instead of reproducing that call, since asserting the
button's own path would only prove the same defect rather than test
``approve_handover``/``confirm_handover``; fixing the missing flag is outside this
patch's write scope (test files only).

Every posting below dates itself ``today()``: Apex Stock Settings ships
``backdating_days = 0`` on this bench, so the ledger refuses any date before today
outright, regardless of what a voucher's own fixture might say.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.api.custody_handover import (
    approve_handover,
    confirm_handover,
    reject_handover,
)
from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    post_stock_entry,
)

test_dependencies = ["Building"]

_ARTICLE = "_T-Custody Article-00001"  # "_Test Blanket"


def _fresh_building():
    building = frappe.copy_doc(frappe.get_test_records("Building")[0])
    building.building_name = f"_T-Handover Building {frappe.generate_hash(length=8)}"
    building.floor_plan = []
    building.insert()
    return building.name


def _seed_store(building, qty):
    post_stock_entry(
        item_type="Custody Article", item=_ARTICLE, qty=qty, building=building,
        voucher_type="Custody Handover", voucher_no=f"_T-Seed-{frappe.generate_hash(length=6)}",
        posting_date=today(),
    )


def _build_handover(from_building, to_building, qty=2, **overrides):
    record = frappe.copy_doc(frappe.get_test_records("Custody Handover")[0])
    record.handover_date = today()
    record.from_building = from_building
    record.to_building = to_building
    record.procurement_supervisor = "test2@example.com"
    record.receiving_supervisor = "test3@example.com"
    record.items = []
    record.append("items", {"item_type": "Custody Article", "item": _ARTICLE, "qty": qty})
    for field, value in overrides.items():
        record.set(field, value)
    return record


def _new_handover(from_building, to_building, qty=2, **overrides):
    record = _build_handover(from_building, to_building, qty=qty, **overrides)
    record.insert()
    return record


class TestCustodyHandover(FrappeTestCase):
    def test_validate_refuses_a_same_building_move_a_shared_supervisor_or_a_non_positive_qty(self):
        """None of these three guards involves the store balance at all."""
        building = _fresh_building()

        same_building = _build_handover(building, building)
        with self.assertRaisesRegex(frappe.ValidationError, "must be different"):
            same_building.insert()

        other_building = _fresh_building()
        same_person = _build_handover(
            building,
            other_building,
            procurement_supervisor="test2@example.com",
            receiving_supervisor="test2@example.com",
        )
        with self.assertRaisesRegex(frappe.ValidationError, "must be different people"):
            same_person.insert()

        zero_qty = _build_handover(building, other_building, qty=0)
        with self.assertRaisesRegex(frappe.ValidationError, "Qty must be greater than zero"):
            zero_qty.insert()

    def test_submit_is_refused_when_the_source_store_cannot_cover_the_quantity(self):
        """The ship leg cannot hand over stock the source store does not hold."""
        empty_building = _fresh_building()
        dest_building = _fresh_building()
        record = _new_handover(empty_building, dest_building, qty=3)

        with self.assertRaisesRegex(frappe.ValidationError, "only 0.0 available"):
            record.submit()

    def test_the_full_review_approve_and_confirm_lifecycle_moves_the_stock(self):
        """The acceptance case: ship on submit, review, approve, confirm — and only
        confirm actually lands the stock in the destination store."""
        source = _fresh_building()
        dest = _fresh_building()
        _seed_store(source, 10)

        record = _new_handover(source, dest, qty=4)
        record.submit()
        code = frappe.response.get("handover_otp")
        self.assertIsNotNone(code)
        self.assertEqual(record.status, "Pending Receipt")
        self.assertEqual(get_store_balance("Custody Article", _ARTICLE, source), 6)
        self.assertEqual(
            get_store_balance("Custody Article", _ARTICLE, dest),
            0,
            "the receive leg must not post until the code is confirmed",
        )

        record.db_set("status", "Under Review")

        approve_handover(record.name, all_items_verified=1)
        self.assertEqual(
            frappe.db.get_value("Custody Handover", record.name, "status"), "Approved"
        )

        confirm_handover(record.name, code)

        self.assertEqual(
            frappe.db.get_value("Custody Handover", record.name, "status"), "Confirmed"
        )
        self.assertEqual(get_store_balance("Custody Article", _ARTICLE, dest), 4)

    def test_confirm_is_refused_to_the_procurement_supervisor_who_shipped_it(self):
        """Separation of duties: the shipper cannot confirm their own delivery."""
        source = _fresh_building()
        dest = _fresh_building()
        _seed_store(source, 10)

        record = _new_handover(source, dest, qty=2, procurement_supervisor="Administrator")
        record.submit()
        code = frappe.response.get("handover_otp")
        record.db_set("status", "Under Review")
        approve_handover(record.name, all_items_verified=1)

        with self.assertRaisesRegex(
            frappe.PermissionError, "cannot confirm their own receipt"
        ):
            confirm_handover(record.name, code)

    def test_rejecting_a_handover_reverses_the_ship_leg(self):
        """A rejection is not a cancel; it must still give the source store its stock back."""
        source = _fresh_building()
        dest = _fresh_building()
        _seed_store(source, 10)

        record = _new_handover(source, dest, qty=4)
        record.submit()
        self.assertEqual(get_store_balance("Custody Article", _ARTICLE, source), 6)

        with self.assertRaisesRegex(frappe.ValidationError, "reason is required"):
            reject_handover(record.name, "")

        reject_handover(record.name, "Wrong item shipped")

        self.assertEqual(
            frappe.db.get_value("Custody Handover", record.name, "status"), "Rejected"
        )
        self.assertEqual(
            get_store_balance("Custody Article", _ARTICLE, source),
            10,
            "rejecting a shipped handover must return its stock to the source store",
        )
