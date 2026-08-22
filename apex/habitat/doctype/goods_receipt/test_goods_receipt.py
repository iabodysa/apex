# Copyright (c) 2026, afmcoltd
"""What Goods Receipt guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``validate``,
``on_submit``, ``before_cancel`` and ``on_cancel``. ``validate`` refuses an intake
building not flagged as a Procurement Intake Store and a non-positive line quantity.
Submitting books every line into the intake store unassigned (nobody's custody yet —
that is Custody Handover's job); cancelling reverses every row this receipt posted.

Every posting below dates itself ``today()``: Apex Stock Settings ships
``backdating_days = 0`` on this bench, so the ledger refuses any date before today
outright, regardless of what a voucher's own fixture might say.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
)

test_dependencies = ["Building", "Custody Article"]

_ARTICLE = "_T-Custody Article-00001"  # "_Test Blanket"


def _fresh_store_building(is_procurement_store=1):
    building = frappe.copy_doc(frappe.get_test_records("Building")[0])
    building.building_name = f"_T-Receipt Building {frappe.generate_hash(length=8)}"
    building.floor_plan = []
    building.is_procurement_store = is_procurement_store
    building.insert()
    return building.name


def _build_receipt(building, qty=10, **overrides):
    record = frappe.copy_doc(frappe.get_test_records("Goods Receipt")[0])
    record.receipt_date = today()
    record.intake_building = building
    record.items = []
    record.append("items", {"item_type": "Custody Article", "item": _ARTICLE, "qty": qty})
    for field, value in overrides.items():
        record.set(field, value)
    return record


class TestGoodsReceipt(FrappeTestCase):
    def test_validate_refuses_a_non_procurement_store_and_a_non_positive_qty(self):
        """Neither guard has anything to do with the ledger."""
        ordinary_building = _fresh_store_building(is_procurement_store=0)
        record = _build_receipt(ordinary_building)
        with self.assertRaisesRegex(frappe.ValidationError, "not flagged as a Procurement"):
            record.insert()

        store_building = _fresh_store_building()
        zero_qty = _build_receipt(store_building, qty=0)
        with self.assertRaisesRegex(frappe.ValidationError, "Qty must be greater than zero"):
            zero_qty.insert()

    def test_submit_books_the_intake_unassigned_and_cancel_reverses_it(self):
        """The acceptance case: goods land in the store with no holder, and cancel
        gives every one of those units back out of the ledger."""
        building = _fresh_store_building()
        record = _build_receipt(building, qty=20)
        record.insert()
        record.submit()

        self.assertEqual(record.status, "Received")
        self.assertEqual(get_store_balance("Custody Article", _ARTICLE, building), 20)

        record.cancel()

        self.assertEqual(
            get_store_balance("Custody Article", _ARTICLE, building),
            0,
            "cancelling a receipt must reverse every unit it booked in",
        )
