# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors

from __future__ import annotations
import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

import apex
from frappe.utils import flt
from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    has_stock_entries,
    post_stock_entry,
)
from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    reverse_stock_entries,
)

# The suite lives outside the app, so the shipped JSON is no longer beside this file;
# it is resolved from the installed package instead.
_DOCTYPES = Path(apex.__file__).resolve().parent / "habitat" / "doctype"
_LEDGER_JSON = _DOCTYPES / "accommodation_stock_ledger" / "accommodation_stock_ledger.json"
_SNAPSHOT_JSON = _DOCTYPES / "occupancy_snapshot" / "occupancy_snapshot.json"

OVERSIGHT_ROLES = ("Finance Manager", "Internal Auditor")
OVERSIGHT_FLAGS = ("read", "report", "export", "print", "email", "share")


def _rows(path, role):
    """The role's permlevel-0 DocPerm rows off the SHIPPED JSON.

    Keyed on the (role, permlevel) PAIR: a permlevel-1 row is not a duplicate of the
    level-0 one, and matching on role alone would conflate them. The file is read
    rather than ``frappe.get_meta`` so the verdict grades what migrate will import,
    not whatever an un-migrated site still holds.
    """
    perms = json.loads(path.read_text(encoding="utf-8"))["permissions"]
    return [p for p in perms if p["role"] == role and int(p.get("permlevel") or 0) == 0]


class TestTheEstateWideOversightGrantIsDeliberate(FrappeTestCase):
    """The owner decision recorded in this module's controller docstring, made falsifiable.

    The grant lets two oversight roles read per-worker custody holdings with a per-person
    value across every building. It was reviewed and KEPT. This asserts the shape that
    decision was taken against, so changing it forces the written reason to be revisited
    instead of the exposure being re-discovered at the next audit.
    """

    def test_both_oversight_roles_hold_one_matching_level_zero_row(self):
        rows = {}
        for role in OVERSIGHT_ROLES:
            found = _rows(_LEDGER_JSON, role)
            self.assertEqual(
                len(found), 1, f"{role} lost or gained a permlevel-0 row on the ledger"
            )
            rows[role] = found[0]
            for flag in OVERSIGHT_FLAGS:
                self.assertEqual(
                    found[0].get(flag), 1, f"{role} permlevel-0 {flag} changed"
                )
        self.assertEqual(
            {k: v for k, v in rows["Finance Manager"].items() if k != "role"},
            {k: v for k, v in rows["Internal Auditor"].items() if k != "role"},
            "the two oversight rows diverged -- they were kept BECAUSE they matched, so "
            "whichever one moved now needs its own recorded reason",
        )

    def test_the_finance_row_is_matched_on_the_occupancy_snapshot(self):
        """The third of the three grants. One grant is a slip; three across two records
        and two roles is the design the decision rests on."""
        found = _rows(_SNAPSHOT_JSON, "Finance Manager")
        self.assertEqual(len(found), 1, "Finance Manager lost its Occupancy Snapshot row")
        for flag in OVERSIGHT_FLAGS:
            self.assertEqual(found[0].get(flag), 1, f"Occupancy Snapshot {flag} changed")

    def test_neither_role_is_row_scoped_to_a_building(self):
        """Why the grant is ESTATE-wide rather than per-building: both roles sit in
        ``HOUSING_UNSCOPED_ROLES``, so the ledger's query condition adds no filter."""
        from apex.habitat.permissions import HOUSING_UNSCOPED_ROLES

        for role in OVERSIGHT_ROLES:
            self.assertIn(
                role,
                HOUSING_UNSCOPED_ROLES,
                f"{role} became building-scoped -- the recorded reason describes an "
                "estate-wide grant and no longer matches the code",
            )

    def test_the_ledger_still_carries_no_permission_levels(self):
        """The reviewability clause. The decision was taken against an all-or-nothing
        record: with no levels, a level-0 read is EVERY field, custodian and unit cost
        included. The day levels arrive, the grant can be narrowed to the fields finance
        needs without touching either role's scope -- so re-read the decision then.
        """
        data = json.loads(_LEDGER_JSON.read_text(encoding="utf-8"))
        self.assertEqual(
            sorted({int(f.get("permlevel") or 0) for f in data["fields"]}),
            [0],
            "a field level appeared -- narrowing this grant is now possible, which is "
            "exactly the condition the recorded decision said to revisit it under",
        )
        self.assertEqual(
            sorted({int(p.get("permlevel") or 0) for p in data["permissions"]}),
            [0],
            "a permlevel-1 DocPerm row appeared on a record with no level-1 fields",
        )


class TestAccommodationStockLedger(FrappeTestCase):
    def test_insert_minimal_ledger_row(self):
        """Smoke test: a minimal valid Stock Ledger row (all mandatory fields set)
        inserts, gets a name, and deletes cleanly. The item / building Links are
        supplied as placeholders with ignore_links=True so the smoke test exercises
        the row write path without standing up the full master chain."""
        doc = frappe.get_doc({
            "doctype": "Accommodation Stock Ledger",
            "naming_series": "ACC-SLE-.YYYY.-.######",
            "posting_date": "2026-06-01",
            "item_type": "Custody Article",
            "item": "SLE-SMOKE-ITEM",
            "signed_qty": 1,
            "building": "SLE-SMOKE-BLDG",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)

        frappe.delete_doc("Accommodation Stock Ledger", doc.name, force=True, ignore_permissions=True)

test_dependencies = ['Building', 'Custody Article', 'Employee']


# --- merged from test_custody_stock_integration.py ---
BUILDING = "_Test Building"
PROCUREMENT_STORE = "_Test Building 2"
class TestCustodyStockIntegration(FrappeTestCase):
    def setUp(self):
        self.article = frappe.db.get_value("Custody Article", {"article_name": "_Test Blanket"})
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})
        # FrappeTestCase rolls the database back once per CLASS, not once per method —
        # frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup — so stock a case
        # leaves in a shared fixture store would become the next case's opening balance. A
        # savepoint is the framework's own way to hand the store back exactly as it was found.
        frappe.db.savepoint("apex_custody_stock_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_custody_stock_case")

    def _balance(self, building, employee=None):
        filters = {"item": self.article, "building": building, "is_cancelled": 0}
        filters["employee"] = employee if employee else ["is", "not set"]
        rows = frappe.get_all("Accommodation Stock Ledger", filters=filters, fields=["signed_qty"])
        return flt(sum(flt(r.signed_qty) for r in rows))

    def _stock_the_store(self, building, qty):
        post_stock_entry(
            item_type="Custody Article", item=self.article, qty=qty, building=building,
            voucher_type="Opening Stock", voucher_no="OPEN-" + frappe.generate_hash(length=12).upper(),
        )

    def _issue(self, qty=5, building=BUILDING, stock_first=True):
        if stock_first:
            self._stock_the_store(building, qty)
        doc = frappe.get_doc({
            "doctype": "Custody Issue",
            "naming_series": "CUST-ISS-.####",
            "issue_date": "2026-05-01",
            "issued_to_employee": self.employee,
            "building": building,
        })
        doc.append("items", {"article": self.article, "qty": qty})
        doc.insert(ignore_permissions=True)
        doc.submit()
        return doc

    def test_an_issue_moves_stock_into_custody_and_a_return_moves_it_back(self):
        issue = self._issue(5)
        self.assertEqual(self._balance(BUILDING, self.employee), 5.0)
        self.assertEqual(self._balance(BUILDING), 0.0)

        returned = frappe.get_doc({
            "doctype": "Custody Return",
            "naming_series": "CUST-RET-.####",
            "return_date": "2026-05-10",
            "custody_issue": issue.name,
            "returned_by_employee": self.employee,
            "building": BUILDING,
        })
        returned.append("items", {"article": self.article, "qty": 5})
        returned.insert(ignore_permissions=True)
        returned.submit()

        self.assertEqual(self._balance(BUILDING, self.employee), 0.0)
        self.assertEqual(self._balance(BUILDING), 5.0)

    def test_cancelling_an_issue_reverses_the_stock_it_moved(self):
        issue = self._issue(3)
        self.assertTrue(has_stock_entries("Custody Issue", issue.name))

        issue.reload()
        issue.cancel()

        self.assertFalse(has_stock_entries("Custody Issue", issue.name))
        self.assertEqual(self._balance(BUILDING, self.employee), 0.0)

    def test_a_receipt_whose_goods_have_been_issued_out_may_not_be_cancelled(self):
        """Cancelling a receipt whose goods already left the store must be refused, not mirrored:
        the reversal would drive the store negative and invent stock that is physically in an
        employee's hands. Nothing may be written on refusal."""
        receipt = frappe.get_doc({
            "doctype": "Goods Receipt",
            "naming_series": "ACC-GRN-.YYYY.-.#####",
            "receipt_date": "2026-05-01",
            "intake_building": PROCUREMENT_STORE,
            "procurement_supervisor": "Administrator",
        })
        receipt.append("items", {"item_type": "Custody Article", "item": self.article, "qty": 10})
        receipt.insert(ignore_permissions=True)
        receipt.submit()
        self.assertEqual(get_store_balance("Custody Article", self.article, PROCUREMENT_STORE), 10.0)

        self._issue(10, building=PROCUREMENT_STORE, stock_first=False)
        self.assertEqual(get_store_balance("Custody Article", self.article, PROCUREMENT_STORE), 0.0)

        receipt.reload()
        with self.assertRaises(frappe.ValidationError):
            receipt.cancel()

        # The refusal fires in before_cancel, which Frappe runs from run_before_save_methods()
        # BEFORE db_update() stamps docstatus 2. Raised from on_cancel instead, the 2 is already
        # written in the open transaction and every read for the rest of the request sees the
        # receipt as cancelled. Reading the row, not the in-memory object: Document._cancel()
        # assigns self.docstatus = 2 before save() is ever called, so the Python attribute is 2
        # either way and proves nothing.
        self.assertEqual(
            frappe.db.get_value("Goods Receipt", receipt.name, "docstatus"), 1,
            "a refused cancel must leave the receipt submitted, not cancelled-in-the-row",
        )
        receipt.reload()
        self.assertEqual(
            receipt.docstatus, 1,
            "reloading the receipt in the same request must still read it as submitted",
        )
        self.assertGreaterEqual(
            get_store_balance("Custody Article", self.article, PROCUREMENT_STORE), 0.0,
            "a refused reversal must never drive the building store negative",
        )
        self.assertEqual(
            frappe.db.count(
                "Accommodation Stock Ledger",
                {"voucher_no": receipt.name, "reversal_of": ["is", "set"]},
            ),
            0,
            "a refused reversal must write no mirror row for the cancelled voucher",
        )


# --- merged from test_stock_ledger_engine.py ---
BUILDING_stock_ledger_engine = "_Test Building"
class TestAccommodationStockLedger_stock_ledger_engine(FrappeTestCase):
    def setUp(self):
        self.article = frappe.db.get_value("Custody Article", {"article_name": "_Test Blanket"})
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})
        self.cost_center = frappe.db.get_value("Building", BUILDING_stock_ledger_engine, "default_cost_center")

    def test_a_posted_entry_carries_the_item_metadata_it_resolved(self):
        name = post_stock_entry(
            item_type="Custody Article", item=self.article, qty=5, building=BUILDING_stock_ledger_engine,
            employee=self.employee, voucher_type="Test Voucher", voucher_no="TV-1",
            voucher_detail_no="r1",
        )
        row = frappe.get_doc("Accommodation Stock Ledger", name)

        self.assertEqual(row.item_name, "_Test Blanket")
        self.assertEqual(row.uom, frappe.db.get_value("Custody Article", self.article, "unit_of_measure"))
        self.assertEqual(flt(row.unit_cost), 12.0)
        self.assertEqual(flt(row.signed_qty), 5.0)
        self.assertEqual(row.cost_center, self.cost_center)
        self.assertEqual(row.employee, self.employee)
        self.assertTrue(has_stock_entries("Test Voucher", "TV-1"))

    def test_a_reversal_nets_the_voucher_to_zero_and_leaves_nothing_live(self):
        post_stock_entry(
            item_type="Custody Article", item=self.article, qty=8, building=BUILDING_stock_ledger_engine,
            voucher_type="Test Voucher", voucher_no="TV-2",
        )
        reverse_stock_entries("Test Voucher", "TV-2")

        rows = frappe.get_all(
            "Accommodation Stock Ledger",
            filters={"voucher_no": "TV-2"},
            fields=["signed_qty", "is_cancelled", "reversal_of"],
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(flt(sum(flt(r.signed_qty) for r in rows)), 0.0)
        self.assertTrue(any(r.reversal_of for r in rows), "a reversal entry must reference the original")
        self.assertFalse(has_stock_entries("Test Voucher", "TV-2"), "no live entries remain after reversal")

    def test_a_drain_entry_carries_a_negative_signed_quantity(self):
        # The engine refuses to move more out of a holder than the holder has, so the custody the
        # drain empties is filled first: posting the -3 straight against an employee holding
        # nothing would be refused by that policy instead of exercised.
        post_stock_entry(
            item_type="Custody Article", item=self.article, qty=3, building=BUILDING_stock_ledger_engine,
            employee=self.employee, voucher_type="Test Voucher", voucher_no="TV-NEG-0",
        )
        name = post_stock_entry(
            item_type="Custody Article", item=self.article, qty=-3, building=BUILDING_stock_ledger_engine,
            employee=self.employee, voucher_type="Test Voucher", voucher_no="TV-NEG-1",
            voucher_detail_no="r1",
        )

        self.assertLess(flt(frappe.db.get_value("Accommodation Stock Ledger", name, "signed_qty")), 0)

    def test_the_ledger_grants_nobody_create(self):
        meta = frappe.get_meta("Accommodation Stock Ledger")
        self.assertFalse(any(p.create for p in meta.permissions), "stock ledger must be read-only")
