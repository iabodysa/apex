# Copyright (c) 2026, afmcoltd
"""What Material Transfer guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``validate``,
``on_submit``, ``before_cancel``/``on_cancel``, and the whitelisted ``mark_received``.
``validate`` refuses a transfer with no items, matching source/destination buildings,
or a non-positive quantity. Submitting refuses a source store that cannot cover the
quantity, else ships the stock out — leaving it in neither store, genuinely in
transit — and only ``mark_received`` lands it in the destination. Cancelling reverses
whichever legs (ship, and receive if it happened) this transfer posted.

Every posting below dates itself ``today()``: Apex Stock Settings ships
``backdating_days = 0`` on this bench, so the ledger refuses any date before today
outright, regardless of what a voucher's own fixture might say.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    post_stock_entry,
)
from apex.habitat.doctype.material_transfer.material_transfer import mark_received

test_dependencies = ["Building", "Custody Article"]

_ARTICLE = "_T-Custody Article-00001"  # "_Test Blanket"


def _fresh_building():
    building = frappe.copy_doc(frappe.get_test_records("Building")[0])
    building.building_name = f"_T-Transfer Building {frappe.generate_hash(length=8)}"
    building.floor_plan = []
    building.insert()
    return building.name


def _seed_store(building, qty):
    post_stock_entry(
        item_type="Custody Article", item=_ARTICLE, qty=qty, building=building,
        voucher_type="Material Transfer", voucher_no=f"_T-Seed-{frappe.generate_hash(length=6)}",
        posting_date=today(),
    )


def _build_transfer(from_building, to_building, qty=1, **overrides):
    record = frappe.copy_doc(frappe.get_test_records("Material Transfer")[0])
    record.transfer_date = today()
    record.from_building = from_building
    record.to_building = to_building
    record.items = []
    record.append("items", {"item_type": "Custody Article", "item": _ARTICLE, "qty": qty})
    for field, value in overrides.items():
        record.set(field, value)
    return record


class TestMaterialTransfer(FrappeTestCase):
    def test_validate_refuses_no_items_a_same_building_move_or_a_non_positive_qty(self):
        """None of these three guards involves the store balance at all."""
        building = _fresh_building()
        other_building = _fresh_building()

        no_items = _build_transfer(building, other_building)
        no_items.items = []
        with self.assertRaisesRegex(frappe.ValidationError, "At least one item is required"):
            no_items.insert()

        same_building = _build_transfer(building, building)
        with self.assertRaisesRegex(frappe.ValidationError, "must be different"):
            same_building.insert()

        zero_qty = _build_transfer(building, other_building, qty=0)
        with self.assertRaisesRegex(frappe.ValidationError, "Qty must be greater than zero"):
            zero_qty.insert()

    def test_submit_is_refused_when_the_source_store_cannot_cover_the_quantity(self):
        """The ship leg cannot take stock the source store does not hold."""
        empty_building = _fresh_building()
        dest_building = _fresh_building()
        record = _build_transfer(empty_building, dest_building, qty=4)
        record.insert()

        with self.assertRaisesRegex(frappe.ValidationError, "only 0.0 available"):
            record.submit()

    def test_submit_ships_the_stock_into_transit_and_mark_received_lands_it(self):
        """The acceptance case: after submit the stock sits in neither store; only
        mark_received actually lands it in the destination."""
        source = _fresh_building()
        dest = _fresh_building()
        _seed_store(source, 10)

        record = _build_transfer(source, dest, qty=6)
        record.insert()
        record.submit()

        self.assertEqual(record.status, "In Transit")
        self.assertEqual(record.issued_by, frappe.session.user)
        self.assertEqual(get_store_balance("Custody Article", _ARTICLE, source), 4)
        self.assertEqual(
            get_store_balance("Custody Article", _ARTICLE, dest),
            0,
            "stock in transit must not yet be in the destination store",
        )

        mark_received(record.name)

        self.assertEqual(
            frappe.db.get_value("Material Transfer", record.name, "status"), "Received"
        )
        self.assertEqual(get_store_balance("Custody Article", _ARTICLE, dest), 6)

    def test_cancelling_after_submit_reverses_the_ship_leg(self):
        """A transfer cancelled while still In Transit must give the source its stock back."""
        source = _fresh_building()
        dest = _fresh_building()
        _seed_store(source, 10)

        record = _build_transfer(source, dest, qty=3)
        record.insert()
        record.submit()

        record.cancel()

        self.assertEqual(get_store_balance("Custody Article", _ARTICLE, source), 10)
        self.assertEqual(get_store_balance("Custody Article", _ARTICLE, dest), 0)

    def test_mark_received_is_refused_on_a_draft_or_an_already_received_transfer(self):
        """The action is fail-closed: only a submitted, In-Transit transfer may be received."""
        source = _fresh_building()
        dest = _fresh_building()
        _seed_store(source, 10)

        draft = _build_transfer(source, dest, qty=2)
        draft.insert()
        with self.assertRaisesRegex(frappe.ValidationError, "Only a submitted transfer"):
            mark_received(draft.name)

        draft.submit()
        mark_received(draft.name)
        self.assertEqual(
            mark_received(draft.name),
            draft.name,
            "receiving an already-Received transfer a second time must be a no-op, not a refusal",
        )
