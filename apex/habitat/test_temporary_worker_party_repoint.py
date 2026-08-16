# Copyright (c) 2026, AFMCO and contributors
"""Linking a Temporary Worker to an Employee has to move his CUSTODY too.

``_repoint_party`` walks ``PARTY_DOCTYPES``, and that dict was the ten housing and custody
TRANSACTION doctypes — not the Accommodation Stock Ledger the transactions post to, and not
the Custody Acknowledgment that evidences receipt. So after a link the source documents said
Employee X while the balance still said Temporary Worker T, and nothing pointed at T any more.

What that costs, in the two places it is read. The checkout clearance gate routes an Employee
party to the ledger's ``employee`` column, finds nothing, and releases a resident who is still
holding the goods. A Custody Return then posts against an Employee holder whose balance is
zero and is refused outright, so the quantity can never come back: out of the store, in nobody's
reachable custody, and still counted in value-at-risk.

The set is not a judgement call, which is why the last test measures it against the schema
rather than against a list someone maintains by hand.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

import apex.habitat.temporary_worker_engine as engine
from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    post_stock_entry,
)

test_dependencies = ["Bed", "Employee", "Custody Article"]

BUILDING = "_Test Building"
ARTICLE = "_T-Custody Article-00001"


def _h():
    return frappe.generate_hash(length=12).upper()


class TestTemporaryWorkerPartyRepoint(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.worker = frappe.get_doc({
            "doctype": "Temporary Worker",
            "worker_name": "TW-" + _h(),
            "passport_number": "P" + _h(),
            "status": "Active",
        })
        self.worker.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})

    def _hand_two_articles_to_the_worker(self):
        """Seed the store, then move two units into the Temporary Worker's custody."""
        voucher = "_T-TWREPOINT-" + _h()[:8]
        post_stock_entry(
            item_type="Custody Article", item=ARTICLE, qty=2, building=BUILDING,
            voucher_type="Goods Receipt", voucher_no=voucher,
        )
        post_stock_entry(
            item_type="Custody Article", item=ARTICLE, qty=-2, building=BUILDING,
            voucher_type="Custody Issue", voucher_no=voucher,
        )
        post_stock_entry(
            item_type="Custody Article", item=ARTICLE, qty=2, building=BUILDING,
            party_type="Temporary Worker", party=self.worker.name,
            voucher_type="Custody Issue", voucher_no=voucher,
        )

    def test_the_ledger_balance_follows_the_worker_to_his_employee(self):
        self._hand_two_articles_to_the_worker()
        employee_before = get_store_balance(
            "Custody Article", ARTICLE, BUILDING, party_type="Employee", party=self.employee
        )
        self.assertEqual(
            get_store_balance(
                "Custody Article", ARTICLE, BUILDING,
                party_type="Temporary Worker", party=self.worker.name,
            ),
            2,
            "the worker has to be holding something before the link can move it",
        )

        engine._repoint_party(self.worker.name, self.employee)

        self.assertEqual(
            get_store_balance(
                "Custody Article", ARTICLE, BUILDING,
                party_type="Temporary Worker", party=self.worker.name,
            ),
            0,
            "the Temporary Worker identity is retired, so nothing may still be held under it",
        )
        self.assertEqual(
            get_store_balance(
                "Custody Article", ARTICLE, BUILDING,
                party_type="Employee", party=self.employee,
            ) - employee_before,
            2,
            "the balance must land on the Employee, or the checkout gate clears a resident "
            "who is still holding the goods and the return is refused for a zero balance",
        )

    def test_the_ledgers_employee_mirror_is_filled_too(self):
        """The clearance gate reads ``employee``, not ``party`` — an unmirrored row is invisible."""
        self._hand_two_articles_to_the_worker()
        engine._repoint_party(self.worker.name, self.employee)

        rows = frappe.get_all(
            "Accommodation Stock Ledger",
            filters={"item": ARTICLE, "party": self.employee, "is_cancelled": 0},
            fields=["employee"],
            limit_page_length=0,
        )
        self.assertTrue(rows, "the re-pointed rows must be findable by the Employee party")
        self.assertTrue(
            all(r.employee == self.employee for r in rows),
            "every re-pointed row must carry the Employee mirror the clearance gate filters on",
        )

    def test_custody_acknowledgment_follows_the_worker(self):
        """The signed receipt names the holder; leaving it behind breaks the audit trail."""
        ack = frappe.get_doc({
            "doctype": "Custody Acknowledgment",
            "custody_issue": "_T-CUSTODY-ISSUE-" + _h()[:8],
            "confirmation_method": "Confirmed Receipt",
            "party_type": "Temporary Worker",
            "party": self.worker.name,
        })
        # The acknowledgement's own lifecycle rule (a submitted Custody Issue behind it)
        # is not what is under test here, and building one would only add a second
        # fixture chain between this case and the party columns it measures.
        ack.flags.ignore_validate = True
        ack.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        engine._repoint_party(self.worker.name, self.employee)

        row = frappe.db.get_value(
            "Custody Acknowledgment", ack.name,
            ["party_type", "party", "acknowledged_by_employee"], as_dict=True,
        )
        self.assertEqual(row.party_type, "Employee")
        self.assertEqual(row.party, self.employee)
        self.assertEqual(row.acknowledged_by_employee, self.employee)

    def test_every_party_bearing_doctype_is_on_the_list(self):
        """A doctype that grows a party column and is not added here silently orphans it."""
        carriers = {
            dt
            for dt in frappe.get_all(
                "DocField",
                filters={"fieldname": "party_type", "parenttype": "DocType"},
                pluck="parent",
            )
            if frappe.db.get_value("DocType", dt, "module")
            in ("Habitat", "Apex Core", "Logistay", "Salis")
        }
        missing = sorted(carriers - set(engine.PARTY_DOCTYPES))
        self.assertEqual(
            missing, [],
            f"these carry party_type but the daily linker never re-points them: {missing}",
        )
