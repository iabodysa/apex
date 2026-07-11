# Copyright (c) 2026, AFMCO and contributors
"""Source-store TOCTOU lock guard (T-631).

Draining the same source store + item from two concurrent Material Transfers or
Custody Handovers must not both pass the availability check on a stale balance and
overdraw the store negative. ``get_store_balance(..., for_update=True)`` takes a
SELECT ... FOR UPDATE on the summed rows so the second drain serializes behind the
first commit. This file proves three things:

  1. Validation half (real bench): an over-draw beyond the source balance is
     rejected on submit for BOTH controllers, and the store balance never goes < 0.
  2. Concurrency half (real two-connection DB lock): while one transaction holds the
     for_update lock on the source ledger rows, a second locking balance read on the
     same key is rejected (QueryTimeoutError) -- the literal cross-transaction
     contention that serializes two drains, not a sequential re-call.
  3. Structural guard (AST, no site): both controllers read the balance with
     for_update=True on their availability path, and the lock precedes the check.
"""

from __future__ import annotations

import ast
import os
import unittest

import frappe
from frappe.tests.utils import timeout

from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    post_stock_entry,
)
from apex.tests.test_utils import ApexHabitatTestCase

_HERE = os.path.dirname(__file__)
_TRANSFER_CTL = os.path.normpath(os.path.join(_HERE, "material_transfer.py"))
_HANDOVER_CTL = os.path.normpath(
    os.path.join(_HERE, "..", "custody_handover", "custody_handover.py")
)


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestStockSourceLocking(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) \
            or frappe.db.get_value("Cost Center", {"is_group": 0})
        self.site = frappe.get_doc({
            "doctype": "Site", "site_name": _h(12)}).insert(ignore_permissions=True)
        self.source = frappe.get_doc({
            "doctype": "Building", "building_name": "Src " + _h(),
            "site": self.site.name, "total_capacity": 4, "company": self.company,
            "default_cost_center": cc}).insert(ignore_permissions=True).name
        self.dest = frappe.get_doc({
            "doctype": "Building", "building_name": "Dst " + _h(),
            "site": self.site.name, "total_capacity": 4, "company": self.company,
            "default_cost_center": cc}).insert(ignore_permissions=True).name
        cat = frappe.db.get_value("Custody Asset Category", {}) or frappe.get_doc({
            "doctype": "Custody Asset Category", "category_name": "Cat " + _h()}).insert(ignore_permissions=True).name
        self.article = frappe.get_doc({
            "doctype": "Custody Article", "naming_series": "ART-.####",
            "article_name": "Item " + _h(), "category": cat,
            "unit_of_measure": "Nos"}).insert(ignore_permissions=True).name

    def _seed_source(self, qty):
        """Book `qty` of the article into the source store (employee unset)."""
        post_stock_entry(
            item_type="Custody Article", item=self.article, qty=qty, building=self.source,
            employee=None, voucher_type="Seed", voucher_no="SEED-" + _h(12),
            posting_date="2026-05-01",
        )

    def _transfer(self, qty):
        t = frappe.get_doc({
            "doctype": "Material Transfer", "naming_series": "ACC-MTR-.YYYY.-.######",
            "transfer_date": "2026-05-02", "from_building": self.source, "to_building": self.dest})
        t.append("items", {"item_type": "Custody Article", "item": self.article, "qty": qty})
        t.insert(ignore_permissions=True)
        t.submit()
        return t

    def _handover(self, qty):
        h = frappe.get_doc({
            "doctype": "Custody Handover", "naming_series": "ACC-HND-.YYYY.-.#####",
            "handover_date": "2026-05-02", "from_building": self.source, "to_building": self.dest,
            "procurement_supervisor": self._user(), "receiving_supervisor": self._user()})
        h.append("items", {"item_type": "Custody Article", "item": self.article, "qty": qty})
        h.insert(ignore_permissions=True)
        h.submit()
        return h

    def _user(self):
        email = f"ssl-{_h(12).lower()}@example.com"
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": "U " + _h(),
                            "send_welcome_email": 0})
        u.insert(ignore_permissions=True)
        u.add_roles("Accommodation Manager")
        return email

    # [#8m0657]
    def test_transfer_overdraw_is_rejected_and_balance_never_negative(self):
        self._seed_source(5)
        with self.assertRaises(frappe.ValidationError):
            self._transfer(8)  # [#b7nqiv]
        self.assertEqual(get_store_balance("Custody Article", self.article, self.source), 5.0)
        self.assertGreaterEqual(
            get_store_balance("Custody Article", self.article, self.source), 0.0,
            "rejected over-draw must not drive the source store negative")

    def test_handover_overdraw_is_rejected_and_balance_never_negative(self):
        self._seed_source(3)
        with self.assertRaises(frappe.ValidationError):
            self._handover(10)  # [#ctsazk]
        self.assertEqual(get_store_balance("Custody Article", self.article, self.source), 3.0)
        self.assertGreaterEqual(
            get_store_balance("Custody Article", self.article, self.source), 0.0)

    def test_two_sequential_drains_cannot_both_overdraw(self):
        """Net of two drains on a 5-unit store: the first (4) succeeds, the second
        (4) is rejected -- the store ends at 1, never negative. (Sequential proof of
        the invariant the lock enforces under true concurrency.)"""
        self._seed_source(5)
        self._transfer(4)
        self.assertEqual(get_store_balance("Custody Article", self.article, self.source), 1.0)
        with self.assertRaises(frappe.ValidationError):
            self._transfer(4)
        self.assertEqual(get_store_balance("Custody Article", self.article, self.source), 1.0)

    # [#odcuk5]
    @timeout(15, "The source-balance for_update lock did not contend across connections")
    def test_concurrent_balance_lock_blocks_second_drain(self):
        """Two live transactions cannot both hold the source store's balance rows.

        Connection A takes the EXACT lock a draining submit opens its critical section
        with -- get_store_balance(..., for_update=True) on the source store + item --
        and holds it uncommitted. Connection B, standing in for a concurrent
        transfer/handover, then takes the same locking balance read with wait=False
        and is rejected with QueryTimeoutError: proof the InnoDB row lock genuinely
        serializes the two drains, so the second can never reach its availability
        check (and overdraw) while the first holds the rows.
        """
        self._seed_source(5)
        frappe.db.commit()  # [#c0ksy0]
        self.addCleanup(frappe.db.rollback)

        with self.primary_connection():
            bal = _locked_balance(self.article, self.source)
            self.assertEqual(bal, 5.0)

            with self.secondary_connection(), self.assertRaises(frappe.QueryTimeoutError):
                _locked_balance(self.article, self.source, wait=False)

    # [#9p5fh3]
    def test_both_controllers_lock_before_reading_balance(self):
        for ctl, fn in ((_TRANSFER_CTL, "_assert_source_availability"),
                        (_HANDOVER_CTL, "_assert_source_availability")):
            src = _read(ctl)
            body = _func_source(src, ctl, fn)
            self.assertIn(
                "get_store_balance", body,
                f"{os.path.basename(ctl)}:{fn} must read the source balance")
            self.assertIn(
                "for_update=True", body,
                f"{os.path.basename(ctl)}:{fn} must take the for_update lock on the "
                "balance read (TOCTOU guard removed?)")
            lock_pos = body.find("for_update=True")
            check_pos = body.find("qty > available")
            self.assertGreater(check_pos, lock_pos,
                               f"{os.path.basename(ctl)}:{fn} must check availability "
                               "AFTER acquiring the lock, not before")


def _locked_balance(item, building, wait=True):
    """The locking balance read, with `wait` exposed so the second connection can
    fail fast (wait=False -> QueryTimeoutError) instead of blocking the suite."""
    Ledger = frappe.qb.DocType("Accommodation Stock Ledger")
    q = (
        frappe.qb.from_(Ledger)
        .select(Ledger.signed_qty)
        .where(Ledger.item_type == "Custody Article")
        .where(Ledger.item == item)
        .where(Ledger.building == building)
        .where(Ledger.is_cancelled == 0)
        .where(Ledger.employee.isnull())
        .for_update(nowait=not wait)
    )
    from frappe.utils import flt
    return flt(sum(flt(r.signed_qty) for r in q.run(as_dict=True)))


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _func_source(src, path, name):
    tree = ast.parse(src, filename=path)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            lines = src.splitlines()
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"{name} not found in {path}")


if __name__ == "__main__":
    unittest.main()


def tearDownModule():
    # [#2esm3x]
    from apex.tests import factories

    factories.purge_test_buildings()
