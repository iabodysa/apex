# Copyright (c) 2026, afmcoltd
"""What Accommodation Stock Ledger guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_permissions.py`` for the declaration assertion and
``frappe/tests/test_document.py`` for the engine behaviour — the DocType's own class
body is ``pass``; everything it guarantees lives in the module-level engine functions
(``post_stock_entry``, ``get_store_balance``, ``has_stock_entries``,
``reverse_stock_entries``, ``validate_reversal_allowed``) that every voucher type
(Custody Handover, Custody Issue, Material Transfer, Goods Receipt) posts through.

The file's own docstring calls out an estate-wide read grant to Finance Manager and
Internal Auditor as a deliberate, reviewable decision, conditioned on this DocType
carrying zero field-level permission overlays — "test_accommodation_stock_ledger
asserts the three grants and the flat level, so a change to either forces this
paragraph to be revisited." That is asserted here directly against
``frappe.get_meta``, per that instruction and per the framework rule that a
permission test asserts the DocPerm declaration itself rather than exercising the
list machinery a permlevel change wouldn't touch.

Every posting below dates itself ``today()``: Apex Stock Settings ships
``backdating_days = 0`` on this bench, so ``post_stock_entry`` refuses any date
before today outright, regardless of what a voucher's own fixture might say.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    has_stock_entries,
    post_stock_entry,
    reverse_stock_entries,
    validate_reversal_allowed,
)

test_dependencies = ["Building", "Custody Article"]


def _fresh_building():
    building = frappe.copy_doc(frappe.get_test_records("Building")[0])
    building.building_name = f"_T-Ledger Building {frappe.generate_hash(length=8)}"
    building.floor_plan = []
    building.insert()
    return building.name


class TestAccommodationStockLedger(FrappeTestCase):
    def test_the_estate_wide_oversight_grant_is_exactly_two_roles_at_a_flat_permission_level(self):
        """The oversight decision this file documents: Finance Manager and Internal
        Auditor read every building's custody unscoped, and the whole DocType sits at
        one permission level so that grant is reviewable rather than a field carve-out."""
        meta = frappe.get_meta("Accommodation Stock Ledger")

        granted_roles = {p.role for p in meta.permissions if p.read}
        self.assertIn("Finance Manager", granted_roles)
        self.assertIn("Internal Auditor", granted_roles)

        self.assertFalse(
            any(getattr(f, "permlevel", 0) for f in meta.fields),
            "a non-zero permlevel would silently narrow the two roles' unscoped read",
        )

    def test_posting_and_reversing_moves_the_store_balance_and_leaves_it_where_it_started(self):
        """The acceptance case: a post moves the balance, and its reversal restores it
        exactly, marking both rows cancelled rather than deleting anything."""
        building = _fresh_building()
        article = frappe.db.get_value(
            "Custody Article", {"article_name": "_Test Blanket"}, "name"
        )

        self.assertEqual(get_store_balance("Custody Article", article, building), 0)

        post_stock_entry(
            item_type="Custody Article", item=article, qty=10, building=building,
            voucher_type="Custody Handover", voucher_no="_T-TV-0001", posting_date=today(),
        )
        self.assertEqual(get_store_balance("Custody Article", article, building), 10)

        self.assertTrue(has_stock_entries("Custody Handover", "_T-TV-0001"))
        self.assertFalse(has_stock_entries("Custody Handover", "_T-Never-Posted"))

        reverse_stock_entries("Custody Handover", "_T-TV-0001")
        self.assertEqual(
            get_store_balance("Custody Article", article, building),
            0,
            "reversing the only posting must return the store to exactly where it started",
        )
        live = frappe.get_all(
            "Accommodation Stock Ledger",
            filters={"voucher_type": "Custody Handover", "voucher_no": "_T-TV-0001", "is_cancelled": 0},
        )
        self.assertEqual(live, [], "both the original and its mirror must be flagged cancelled")

    def test_a_posting_that_would_drive_the_store_negative_is_refused(self):
        """The engine's own negative-stock policy: an issue cannot exceed what the store holds."""
        building = _fresh_building()
        article = frappe.db.get_value(
            "Custody Article", {"article_name": "_Test Pillow"}, "name"
        )
        post_stock_entry(
            item_type="Custody Article", item=article, qty=5, building=building,
            voucher_type="Custody Handover", voucher_no="_T-TV-0002", posting_date=today(),
        )

        with self.assertRaisesRegex(frappe.ValidationError, "holds only"):
            post_stock_entry(
                item_type="Custody Article", item=article, qty=-6, building=building,
                voucher_type="Custody Handover", voucher_no="_T-TV-0003", posting_date=today(),
            )

    def test_reversing_an_earlier_posting_is_refused_once_a_later_one_has_drained_the_store(self):
        """A reversal must unwind in order: the earlier posting cannot be reversed
        while a later one has already taken the stock it would give back."""
        building = _fresh_building()
        article = frappe.db.get_value(
            "Custody Article", {"article_name": "_Test Blanket"}, "name"
        )
        post_stock_entry(
            item_type="Custody Article", item=article, qty=10, building=building,
            voucher_type="Custody Handover", voucher_no="_T-TV-0004", posting_date=today(),
        )
        post_stock_entry(
            item_type="Custody Article", item=article, qty=-8, building=building,
            voucher_type="Custody Handover", voucher_no="_T-TV-0005", posting_date=today(),
        )

        with self.assertRaisesRegex(frappe.ValidationError, "Reverse the later movements first"):
            validate_reversal_allowed("Custody Handover", "_T-TV-0004")
