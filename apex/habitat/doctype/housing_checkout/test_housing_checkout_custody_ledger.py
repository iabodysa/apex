# Copyright (c) 2026, afmcoltd
"""What check-out does to the custody the resident was holding.

Check-in credits the resident's name on the Accommodation Stock Ledger. Check-out has to
debit it again, or the departed resident keeps a custody balance forever and the building
store stays permanently short by whatever came back — until the phantom shortage starts
refusing legitimate issues, with no manual correction path, because the ledger is
``in_create`` and no role holds create or write on it.

The store mirror is what separates the two shapes: goods that came back re-enter the
store, goods recorded Lost or Damaged leave the holder without re-entering anywhere.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    has_stock_entries,
    post_stock_entry,
)

# Project is deliberately not a dependency: ERPNext's fixture is not idempotent — its
# autoname mints a new name while project_name carries a unique index, so a second build
# collides instead of being skipped. The one already on the site is read instead.
test_dependencies = ["Bed", "Employee", "Custody Article"]

BUILDING = "_Test Building"
ROOM = "_T-101"
ARTICLE = "_T-Custody Article-00005"


def _holder_balance(party_type, party, article):
    rows = frappe.get_all(
        "Accommodation Stock Ledger",
        filters={
            "item": article,
            "party_type": party_type,
            "party": party,
            "is_cancelled": 0,
        },
        pluck="signed_qty",
    )
    return sum(rows)


class TestHousingCheckoutCustodyLedger(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})
        self.project = frappe.db.get_value("Project", {"project_name": "_Test Project"})
        self.bed = frappe.db.get_value("Bed", {"room": ROOM, "status": "Available"})
        # FrappeTestCase rolls the database back once per CLASS, not per method
        # (frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup), and a
        # checkout leaves the room Needs Cleaning — which the next check-in refuses. The
        # room and bed are shared fixtures, so they are handed back as they were found.
        self.addCleanup(frappe.db.set_value, "Room", ROOM, "readiness_status", "Ready")
        self.addCleanup(frappe.db.set_value, "Bed", self.bed, "status", "Available")
        # The store has to hold the article before it can be handed over — the check-in
        # gate refuses moving more than the building has.
        post_stock_entry(
            item_type="Custody Article", item=ARTICLE, qty=5, building=BUILDING,
            voucher_type="Goods Receipt", voucher_no=f"_T-SEED-{frappe.generate_hash(length=12)}",
        )

    def _check_in(self):
        assignment = frappe.get_doc({
            "doctype": "Housing Assignment",
            "party_type": "Employee",
            "party": self.employee,
            "building": BUILDING,
            "room": ROOM,
            "bed": self.bed,
            "assignment_type": "New Assignment",
            "stay_type": "Permanent",
            "check_in_date": "2026-05-01",
            "project": self.project,
            "custody_items": [{"article": ARTICLE, "quantity": 2}],
        })
        assignment.insert(ignore_permissions=True)
        assignment.submit()
        # The drain is gated on this leg existing, so a failure here means the test never
        # reached the behaviour it exists to check — not that the behaviour is wrong.
        self.assertTrue(
            has_stock_entries("Housing Assignment", assignment.name),
            "check-in must post the holder leg, or there is nothing for check-out to debit",
        )
        return assignment

    def _check_out(self, assignment, return_status, quantity_returned):
        checkout = frappe.get_doc({
            "doctype": "Housing Checkout",
            "assignment": assignment.name,
            "checkout_date": "2026-06-01",
            "checkout_reason": "End of Contract",
            "custody_return_items": [{
                "article": ARTICLE,
                "quantity_issued": 2,
                "quantity_returned": quantity_returned,
                "return_status": return_status,
            }],
        })
        checkout.insert(ignore_permissions=True)
        checkout.submit()
        return checkout

    # Both cases measure a DELTA, never an absolute. FrappeTestCase rolls back once per
    # class, so the first case's ledger rows are still standing when the second runs, and
    # an absolute balance would read the sum of both.

    def test_returned_custody_leaves_the_resident_and_re_enters_the_store(self):
        holder_before = _holder_balance("Employee", self.employee, ARTICLE)
        store_before = get_store_balance("Custody Article", ARTICLE, BUILDING)
        assignment = self._check_in()

        self.assertEqual(
            _holder_balance("Employee", self.employee, ARTICLE) - holder_before, 2,
            "check-in must credit the resident, or there is nothing for check-out to debit",
        )

        self._check_out(assignment, "Returned", 2)

        self.assertEqual(
            _holder_balance("Employee", self.employee, ARTICLE), holder_before,
            "the resident leaves holding exactly what they arrived holding",
        )
        self.assertEqual(
            get_store_balance("Custody Article", ARTICLE, BUILDING), store_before,
            "and the returned goods are back in the building store",
        )

    def test_lost_custody_leaves_the_resident_without_re_entering_the_store(self):
        holder_before = _holder_balance("Employee", self.employee, ARTICLE)
        store_before = get_store_balance("Custody Article", ARTICLE, BUILDING)
        assignment = self._check_in()
        self._check_out(assignment, "Lost", 0)

        self.assertEqual(
            _holder_balance("Employee", self.employee, ARTICLE), holder_before,
            "a lost article still leaves the resident's custody — they are no longer holding it",
        )
        self.assertEqual(
            get_store_balance("Custody Article", ARTICLE, BUILDING), store_before - 2,
            "and it must NOT come back into the store, because it is gone",
        )
