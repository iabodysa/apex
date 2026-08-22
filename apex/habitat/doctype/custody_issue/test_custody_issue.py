# Copyright (c) 2026, afmcoltd
"""What Custody Issue guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``validate``,
``on_submit``, ``before_cancel`` and ``on_cancel``. ``validate`` refuses a non-positive
quantity and a serialized article missing its serial number or issued at any quantity
but one, freezes each line's unit value from the article master the first time it is
blank, and defaults the expected return date from the longest custody window among the
issued articles' categories. Submitting refuses a building store that cannot cover the
quantity, then moves the stock from the store into the holder's custody; cancelling
reverses that same movement and un-names the issuer.

Every posting below dates itself ``today()``: Apex Stock Settings ships
``backdating_days = 0`` on this bench, so the ledger refuses any date before today
outright, regardless of what a voucher's own fixture might say.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    post_stock_entry,
)

test_dependencies = ["Building", "Employee", "Custody Asset Category"]


def _fresh_building():
    building = frappe.copy_doc(frappe.get_test_records("Building")[0])
    building.building_name = f"_T-Issue Building {frappe.generate_hash(length=8)}"
    building.floor_plan = []
    building.insert()
    return building.name


def _fresh_category(default_custody_days=0):
    category = frappe.get_doc(
        {
            "doctype": "Custody Asset Category",
            "category_name": f"_T-Issue Category {frappe.generate_hash(length=6)}",
            "default_custody_days": default_custody_days,
        }
    ).insert()
    return category.name


def _fresh_article(category, standard_unit_cost=12, is_serialized=0):
    article = frappe.get_doc(
        {
            "doctype": "Custody Article",
            "article_name": f"_T-Issue Article {frappe.generate_hash(length=6)}",
            "category": category,
            "standard_unit_cost": standard_unit_cost,
            "is_serialized": is_serialized,
        }
    ).insert()
    return article.name


def _seed_store(building, article, qty):
    post_stock_entry(
        item_type="Custody Article", item=article, qty=qty, building=building,
        voucher_type="Custody Issue", voucher_no=f"_T-Seed-{frappe.generate_hash(length=6)}",
        posting_date=today(),
    )


def _build_issue(building, article, qty=1, **overrides):
    record = frappe.copy_doc(frappe.get_test_records("Custody Issue")[0])
    record.issue_date = today()
    record.building = building
    record.party_type = "Employee"
    record.party = None
    record.issued_to_employee = None
    record.issued_to_name = None
    record.expected_return_date = None
    record.items = []
    record.append("items", {"article": article, "qty": qty})
    for field, value in overrides.items():
        record.set(field, value)
    return record


class TestCustodyIssue(FrappeTestCase):
    def test_validate_refuses_a_non_positive_qty(self):
        """A row cannot claim to issue zero or fewer units of anything."""
        building = _fresh_building()
        category = _fresh_category()
        article = _fresh_article(category)

        record = _build_issue(building, article, qty=0)
        with self.assertRaisesRegex(frappe.ValidationError, "Qty must be greater than zero"):
            record.insert()

    def test_validate_refuses_a_serialized_article_with_no_serial_or_more_than_one_unit(self):
        """A serialized article is one physical unit per line."""
        building = _fresh_building()
        category = _fresh_category()
        article = _fresh_article(category, is_serialized=1)

        no_serial = _build_issue(building, article, qty=1)
        with self.assertRaisesRegex(frappe.ValidationError, "Serial No is required"):
            no_serial.insert()

        too_many = _build_issue(building, article, qty=2)
        too_many.items[0].serial_no = "SN-0001"
        with self.assertRaisesRegex(frappe.ValidationError, "Qty must be 1"):
            too_many.insert()

    def test_validate_freezes_the_unit_value_and_defaults_the_return_date(self):
        """The value printed on the receipt must be the one the worker signed for,
        and the return date defaults from the longest window among the categories."""
        building = _fresh_building()
        category = _fresh_category(default_custody_days=45)
        article = _fresh_article(category, standard_unit_cost=99)

        record = _build_issue(building, article, qty=1)
        record.insert()

        self.assertEqual(record.items[0].unit_value, 99)
        self.assertEqual(
            getdate(record.expected_return_date), getdate(add_days(today(), 45))
        )

        record.items[0].article = None  # article's cost must never overwrite an already-signed value
        record.reload()
        self.assertEqual(record.items[0].unit_value, 99)

    def test_submit_is_refused_when_the_store_cannot_cover_the_quantity(self):
        """Issuing must not drive the building store negative."""
        building = _fresh_building()
        category = _fresh_category()
        article = _fresh_article(category)

        record = _build_issue(building, article, qty=3, issued_to_employee="_T-Employee-00001")
        record.insert()

        with self.assertRaisesRegex(frappe.ValidationError, "only 0.0 available"):
            record.submit()

    def test_submit_moves_stock_into_custody_and_cancel_reverses_it(self):
        """The acceptance case: submit hands the stock to the worker; cancel gives it back."""
        building = _fresh_building()
        category = _fresh_category()
        article = _fresh_article(category)
        _seed_store(building, article, 5)

        record = _build_issue(
            building, article, qty=2, issued_to_employee="_T-Employee-00001"
        )
        record.insert()
        record.submit()

        self.assertEqual(record.status, "Issued")
        self.assertEqual(record.issued_by, frappe.session.user)
        self.assertEqual(get_store_balance("Custody Article", article, building), 3)
        self.assertEqual(
            get_store_balance("Custody Article", article, building, employee="_T-Employee-00001"),
            2,
        )

        record.cancel()

        self.assertEqual(get_store_balance("Custody Article", article, building), 5)
        self.assertEqual(
            get_store_balance("Custody Article", article, building, employee="_T-Employee-00001"),
            0,
        )
        self.assertIsNone(
            frappe.db.get_value("Custody Issue", record.name, "issued_by"),
            "cancelling must un-name the issuer",
        )
