# Copyright (c) 2026, AFMCO and contributors
"""Utility Bill Entry -> Accommodation Ledger money trail.

Proves the financial side effects of habitat/doctype/utility_bill_entry:
- on_submit posts exactly ONE Accommodation Ledger row carrying the building's
  share (total_site_cost == bill_amount, no reversal_of);
- on_cancel posts a SECOND, offsetting row (total_site_cost negative,
  reversal_of == the original row) -- the reversal that keeps the building cost
  allocation balanced;
- before_cancel refuses only, so a cancel blocked after it has run leaves no
  offsetting row behind;
- a FAILED post hands the caller the real exception and leaves rows written
  earlier in the same request alone, rather than rolling the whole transaction
  back behind a generic message;
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

from apex.tests._helpers import submit_via_workflow


def _hash(n: int = 12) -> str:
    return frappe.generate_hash(length=n).upper()


_NOT_REVERSAL = ["is", "not set"]

_REFUSING_HANDLER = (
    "apex.habitat.doctype.utility_bill_entry."
    "test_utility_bill_ledger_posting.refuse_cancel"
)


def refuse_cancel(doc, method=None):
    """Test-only SECOND before_cancel handler for Utility Bill Entry.

    Registered at the END of the doctype's before_cancel handler list so it
    runs AFTER the controller's own: Document.hook's compose calls the class
    method first, then each doc_events handler in list order
    (frappe/model/document.py:1354-1374). Raises the exception class directly
    rather than through frappe.throw so this refusal never enters the
    translation surface.
    """
    raise frappe.ValidationError("Utility Bill Entry cancel refused after before_cancel")


class TestUtilityBillLedgerPosting(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName + _hash()
        self.building = frappe.get_doc({
            "doctype": "Building",
            "building_name": f"UBL {tag}",
            "abbreviation": "U" + _hash(),
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


    def test_seed_is_present(self):
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
        submit_via_workflow(bill)

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

    def _witness_row(self):
        """A Site row: one mandatory Data field, no links, and nothing else in this
        module touches it, so its survival isolates the transaction behaviour from
        the submit's own ledger side effect."""
        return frappe.get_doc({
            "doctype": "Site", "site_name": "A332-UBE-" + _hash(),
        }).insert(ignore_permissions=True).name

    def test_a_failed_post_keeps_rows_written_earlier_in_the_same_request(self):
        """on_submit must not wrap _post_ledger_row in ``except Exception:
        frappe.db.rollback(); frappe.throw(generic)``: frappe.db.rollback() takes no
        savepoint, so it would discard the WHOLE request transaction — every row written
        before the submit was reached, not just this bill — and the generic message
        would then stand in for the error that actually failed the post.

        Both halves are graded: the caller is handed the original exception (a
        RuntimeError, where the wrapper would have converted it to a
        frappe.ValidationError carrying no cause), and a row written earlier in the
        same request outlives the failure.

        docstatus is deliberately NOT asserted. db_update() stamps docstatus 1
        (frappe/model/document.py:428) before run_post_save_methods() dispatches
        on_submit (:431), so with the wrapper gone the stamp survives inside this
        still-open test transaction. A real request unwinds it at the request
        boundary; asserting it here would grade the absence of that boundary in the
        test harness, not the product.
        """
        from unittest.mock import patch

        witness = self._witness_row()
        bill = self._bill(bill_amount=1200)
        bill.insert(ignore_permissions=True)

        with patch(
            "apex.habitat.doctype.utility_bill_entry.utility_bill_entry._post_ledger_row",
            side_effect=RuntimeError("accommodation ledger insert failed"),
        ):
            with self.assertRaises(RuntimeError) as caught:
                submit_via_workflow(bill)

        self.assertIn(
            "accommodation ledger insert failed", str(caught.exception),
            "the real error must reach the caller instead of a generic message that "
            "names neither the failing step nor its cause",
        )
        self.assertTrue(
            frappe.db.exists("Site", witness),
            "a failed post must not discard rows this request wrote before it",
        )
        self.assertTrue(
            frappe.db.exists("Building", self.building),
            "the fixtures this test set up must outlive the failed post too",
        )

    def test_cancel_posts_signed_reversal_referencing_the_original(self):
        bill = self._bill(bill_amount=1200)
        bill.insert(ignore_permissions=True)
        submit_via_workflow(bill)

        original = self._ledger_rows(bill.name, reversal=False)
        self.assertEqual(len(original), 1, "precondition: one period row exists")
        original_name = original[0].name

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
        all_rows = self._ledger_rows(bill.name)
        self.assertEqual(len(all_rows), 2, "post + reversal = two rows total")
        self.assertEqual(
            flt(sum(flt(r.total_site_cost) for r in all_rows)), 0.0,
            "post and reversal must net to zero",
        )

    def _refuse_cancel_after_before_cancel(self):
        """Append refuse_cancel to Utility Bill Entry's before_cancel handlers.

        frappe.local.doc_events_hooks is a process global that no test rollback
        undoes, so the patch is a fresh copy and cleanup restores the original
        dict BY IDENTITY -- mutating the cached dict in place would leak the
        extra handler into every later test sharing this process.
        """
        original = frappe.get_doc_hooks()
        patched = {
            doctype: {event: list(handlers) for event, handlers in events.items()}
            for doctype, events in original.items()
        }
        patched.setdefault("Utility Bill Entry", {}).setdefault(
            "before_cancel", []
        ).append(_REFUSING_HANDLER)

        self.addCleanup(setattr, frappe.local, "doc_events_hooks", original)
        frappe.local.doc_events_hooks = patched
        self.assertIs(
            frappe.get_doc_hooks(), patched,
            "the refusing handler must be the live hook table, not a discarded copy",
        )

    def test_a_refusal_after_before_cancel_posts_no_reversal(self):
        """A cancel refused once before_cancel has run must leave the ledger clean.

        Frappe dispatches every before_cancel handler from
        run_before_save_methods() (frappe/model/document.py:414), strictly
        before db_update() stamps docstatus 2 (:428) and before on_cancel runs
        (:431). The controller's before_cancel only reads, so a refusal raised
        after it aborts the cancel with nothing written -- where an insert done
        from before_cancel would leave an offsetting row on the books for a
        cancel that never completed.
        """
        bill = self._bill(bill_amount=1200)
        bill.insert(ignore_permissions=True)
        submit_via_workflow(bill)
        self.assertEqual(
            len(self._ledger_rows(bill.name, reversal=False)), 1,
            "precondition: one period row exists",
        )

        self._refuse_cancel_after_before_cancel()

        bill.reload()
        bill.cancellation_reason = "QA refusal"
        with self.assertRaises(frappe.ValidationError):
            bill.cancel()

        # docstatus is NOT evidence of a refusal: Document._cancel() assigns
        # self.docstatus = 2 (frappe/model/document.py:1085) before save() is
        # ever called, so the in-memory attribute reads 2 whichever hook
        # refused. Grade the stored row, then a reload.
        self.assertEqual(
            frappe.db.get_value("Utility Bill Entry", bill.name, "docstatus"), 1,
            "a refused cancel must leave the bill submitted, not cancelled-in-the-row",
        )
        bill.reload()
        self.assertEqual(
            bill.docstatus, 1,
            "reloading the bill in the same request must still read it as submitted",
        )
        self.assertEqual(
            frappe.db.count(
                "Accommodation Ledger",
                {
                    "source_doctype": "Utility Bill Entry",
                    "source_name": bill.name,
                    "reversal_of": ["is", "set"],
                },
            ),
            0,
            "a refused cancel must post no offsetting Accommodation Ledger row",
        )

    def test_shared_meter_posts_only_the_bearing_share(self):
        bill = self._bill(total_bill_amount=1000, cost_bearing_pct=40)
        bill.insert(ignore_permissions=True)
        self.assertEqual(
            flt(bill.bill_amount), 400.0,
            "shared-meter share must be total * pct/100",
        )

        submit_via_workflow(bill)
        rows = self._ledger_rows(bill.name, reversal=False)
        self.assertEqual(len(rows), 1, "submit posts one row")
        self.assertEqual(
            flt(rows[0].total_site_cost), 400.0,
            "the ledger must carry the building's share, not the full invoice",
        )
