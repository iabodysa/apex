# Copyright (c) 2026, AFMCO and contributors
"""Utility Bill Entry -> Accommodation Ledger money trail.

Proves the financial side effects of habitat/doctype/utility_bill_entry:
- on_submit posts exactly ONE Accommodation Ledger row carrying the building's
  share (total_site_cost == bill_amount, no reversal_of);
- before_cancel posts a SECOND, offsetting row (total_site_cost negative,
  reversal_of == the original row) -- the reversal that keeps the building cost
  allocation balanced;
- _compute_sharing turns a shared-meter invoice (total_bill_amount +
  cost_bearing_pct) into the posted building share.

The existing utility_bill_entry / qa_probe tests only cover insert / mandatory /
period-order / duplicate-period; none submits-and-asserts-a-ledger-row nor
cancels-and-asserts-a-reversal. A regression dropping the post, mis-signing the
reversal, or breaking the bearing share would otherwise pass silently.

Fields/options below are verified against the DocType JSON under
habitat/doctype (utility_bill_entry, accommodation_ledger, utility_account,
accommodation_building); nothing is guessed.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt


def _hash(n: int = 6) -> str:
    return frappe.generate_hash(length=n).upper()


# Reversal rows carry reversal_of; the period post does not. This filter isolates
# the single non-reversal post the controller emits on submit.
_NOT_REVERSAL = ["is", "not set"]


class TestUtilityBillLedgerPosting(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # [#fixtures] Per-test unique keys so reruns never collide and assertions
        # can scope to THIS test's building/account only.
        tag = self._testMethodName + _hash()
        # total_capacity is read_only in metadata but is dict-set on insert; the
        # cancel path reads building.total_capacity, so seed a real non-zero value.
        self.building = frappe.get_doc({
            "doctype": "Building",
            "building_name": f"UBL {tag}",
            "abbreviation": "U" + _hash(3),
            "status": "Active",
            "total_capacity": 50,
        }).insert(ignore_permissions=True).name
        self.account = frappe.get_doc({
            "doctype": "Utility Account",
            "naming_series": "UTIL-ACC-.####",
            "building": self.building,
            "utility_type": "Electricity",
            "account_number": "UBL-ACC-" + _hash(),
        }).insert(ignore_permissions=True).name

    def tearDown(self):
        frappe.set_user("Administrator")

    # helpers

    def _bill(self, **overrides):
        """Build a Utility Bill Entry on this test's account.

        building/utility_type are fetch_from the real Utility Account, so the
        controller's doc.building / doc.utility_type resolve to real records.
        """
        data = {
            "doctype": "Utility Bill Entry",
            "naming_series": "UTIL-BILL-.YYYY.-.#####",
            "utility_account": self.account,
            "billing_period_from": "2026-04-01",
            "billing_period_to": "2026-04-30",
            "bill_amount": 1200,
        }
        data.update(overrides)
        return frappe.get_doc(data)

    def _ledger_rows(self, bill_name, reversal=None):
        """Rows the controller posted for this bill.

        reversal=None: all; True: only reversal rows; False: only the period post.
        Partitioned in Python on reversal_of truthiness (the same approach as
        test_accommodation_stock_ledger) to stay independent of any specific
        "is set" filter operator -- only the verified ["is", "not set"] is used
        at the DB layer, for the period-post path.
        """
        if reversal is False:
            filters = {
                "source_doctype": "Utility Bill Entry",
                "source_name": bill_name,
                "reversal_of": _NOT_REVERSAL,
            }
            return frappe.get_all(
                "Accommodation Ledger",
                filters=filters,
                fields=["name", "total_site_cost", "reversal_of", "ledger_type"],
            )
        rows = frappe.get_all(
            "Accommodation Ledger",
            filters={"source_doctype": "Utility Bill Entry", "source_name": bill_name},
            fields=["name", "total_site_cost", "reversal_of", "ledger_type"],
        )
        if reversal is True:
            return [r for r in rows if r.reversal_of]
        return rows

    # tests

    def test_seed_is_present(self):
        # [#non-vacuous] Guard the whole file: if the seed silently failed, the
        # submit/cancel assertions below would pass vacuously against zero rows.
        self.assertTrue(
            frappe.db.exists("Building", self.building),
            "seed building must exist",
        )
        self.assertTrue(
            frappe.db.exists("Utility Account", self.account),
            "seed utility account must exist",
        )
        self.assertEqual(
            frappe.db.get_value("Utility Account", self.account, "building"),
            self.building,
            "the seeded account must point at the seeded building",
        )

    def test_submit_posts_one_ledger_row_for_the_period(self):
        bill = self._bill(bill_amount=1200)
        bill.insert(ignore_permissions=True)
        bill.submit()

        # The fetch_from must have resolved the building the controller posts to.
        self.assertEqual(bill.building, self.building, "building must fetch from the account")

        rows = self._ledger_rows(bill.name, reversal=False)
        self.assertEqual(len(rows), 1, "submit must post exactly one period ledger row")
        row = rows[0]
        self.assertEqual(
            flt(row.total_site_cost), 1200.0,
            "the posted row must carry the building's bill_amount",
        )
        self.assertFalse(row.reversal_of, "the period post is not a reversal")
        self.assertEqual(row.ledger_type, "Electricity", "ledger_type mirrors the utility type")

    def test_cancel_posts_signed_reversal_referencing_the_original(self):
        bill = self._bill(bill_amount=1200)
        bill.insert(ignore_permissions=True)
        bill.submit()

        original = self._ledger_rows(bill.name, reversal=False)
        self.assertEqual(len(original), 1, "precondition: one period row exists")
        original_name = original[0].name

        # cancellation_reason is mandatory in before_cancel; set on the submitted doc.
        bill.reload()
        bill.cancellation_reason = "QA reversal"
        bill.cancel()

        reversals = self._ledger_rows(bill.name, reversal=True)
        self.assertEqual(len(reversals), 1, "cancel must post exactly one reversal row")
        rev = reversals[0]
        self.assertEqual(
            rev.reversal_of, original_name,
            "the reversal must reference the original period row",
        )
        self.assertEqual(
            flt(rev.total_site_cost), -1200.0,
            "the reversal must carry the negated bill_amount",
        )
        # Money trail nets to zero across the two rows.
        all_rows = self._ledger_rows(bill.name)
        self.assertEqual(len(all_rows), 2, "post + reversal = two rows total")
        self.assertEqual(
            flt(sum(flt(r.total_site_cost) for r in all_rows)), 0.0,
            "post and reversal must net to zero",
        )

    def test_shared_meter_posts_only_the_bearing_share(self):
        # total 1000 borne at 40% => building share 400 (_compute_sharing).
        bill = self._bill(total_bill_amount=1000, cost_bearing_pct=40)
        # bill_amount is recomputed from the total/pct on validate; the seeded
        # default must NOT survive.
        bill.insert(ignore_permissions=True)
        self.assertEqual(
            flt(bill.bill_amount), 400.0,
            "shared-meter share must be total * pct/100",
        )

        bill.submit()
        rows = self._ledger_rows(bill.name, reversal=False)
        self.assertEqual(len(rows), 1, "submit posts one row")
        self.assertEqual(
            flt(rows[0].total_site_cost), 400.0,
            "the ledger must carry the building's share, not the full invoice",
        )
