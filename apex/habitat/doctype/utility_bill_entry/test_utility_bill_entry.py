# Copyright (c) 2026, afmcoltd
"""What a Utility Bill Entry guarantees, asserted against the DocType itself.

Patterned on frappe's own document lifecycle tests (``frappe/tests/test_document.py``,
``test_validate`` / ``test_update_after_submit``) for the ``validate`` refusals and
computed fields, and on ``test_docstatus.py`` for the submit/cancel half. ``validate`` and
``on_submit``/``before_cancel`` are module-level functions wired through ``hooks.py``'s
``doc_events``; ``on_cancel`` is a genuine method on the ``Document`` subclass. All run
only through the real lifecycle calls exercised below.

Each test uses its own non-overlapping billing period on the same Utility Account,
because ``validate`` refuses two Utility Bill Entries whose periods overlap for the same
account — and this test class's own rollback only happens once, at class teardown, so
rows from earlier methods in this class are still standing when a later method runs.

The central guarantee, called out explicitly for this app's ledgers: ``on_submit`` posts
one Accommodation Ledger row per bill, keyed by ``_live_ledger_row`` rather than a DB
unique index — posting the same bill's hook twice must still leave exactly one live row.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Utility Account", "Building"]


def _new_bill(period_from, period_to, **fields):
    account = frappe.db.get_value(
        "Utility Account", {"account_number": "_T-UTIL-ELEC-001"}, "name"
    )
    bill = frappe.new_doc("Utility Bill Entry")
    bill.utility_account = account
    bill.billing_period_from = period_from
    bill.billing_period_to = period_to
    bill.bill_amount = fields.pop("bill_amount", 100)
    for fieldname, value in fields.items():
        bill.set(fieldname, value)
    return bill


class TestUtilityBillEntry(FrappeTestCase):
    def test_a_current_reading_lower_than_the_previous_is_refused(self):
        """A current reading below the previous one is a broken meter or a typo, not a
        real consumption figure."""
        bill = _new_bill(
            "2026-01-01",
            "2026-01-31",
            meter_reading_previous=500,
            meter_reading_current=400,
        )

        with self.assertRaisesRegex(
            frappe.ValidationError, "cannot be lower than the Previous"
        ):
            bill.insert()

    def test_meter_units_consumed_is_derived_from_the_readings(self):
        """The acceptance counterpart to the refusal above — valid readings must still
        derive consumed units, not just avoid the refusal."""
        bill = _new_bill(
            "2026-02-01",
            "2026-02-28",
            meter_reading_previous=500,
            meter_reading_current=620,
        )

        bill.insert()

        self.assertEqual(bill.meter_units_consumed, 120)

    def test_a_shared_meters_building_share_is_the_stated_percentage_of_the_total(self):
        """A shared meter must bill only this building's percentage of the invoice, with
        the full total and percentage kept for the audit trail."""
        bill = _new_bill(
            "2026-03-01", "2026-03-31", total_bill_amount=1000, cost_bearing_pct=40
        )

        bill.insert()

        self.assertEqual(bill.bill_amount, 400)
        self.assertIn("40.0", bill.bill_share_note)

    def test_a_billing_period_ending_before_it_starts_is_refused(self):
        """A period that ends before it starts cannot be the subject of a real invoice."""
        bill = _new_bill("2026-04-30", "2026-04-01")

        with self.assertRaisesRegex(frappe.ValidationError, "must be on or after"):
            bill.insert()

    def test_a_negative_bill_amount_is_refused(self):
        """A bill entry represents money owed, so a negative amount is a data-entry
        error, not a credit."""
        bill = _new_bill("2026-06-01", "2026-06-30", bill_amount=-50)

        with self.assertRaisesRegex(frappe.ValidationError, "cannot be negative"):
            bill.insert()

    def test_submitting_the_same_bill_twice_posts_only_one_live_ledger_row(self):
        """``_post_ledger_row`` is keyed on ``_live_ledger_row`` rather than a DB unique
        index, so the on_submit hook is invoked a second time directly here — frappe's
        own docstatus guard already blocks a real second ``submit()`` through the API, so
        this simulates the one path (a retried hook, a race) the app-level guard exists
        for."""
        from apex.habitat.doctype.utility_bill_entry.utility_bill_entry import on_submit

        bill = _new_bill("2026-05-01", "2026-05-31", bill_amount=250)
        bill.insert()
        bill.submit()

        on_submit(bill)

        self.assertEqual(
            frappe.db.count(
                "Accommodation Ledger",
                {
                    "source_doctype": "Utility Bill Entry",
                    "source_name": bill.name,
                    "reversal_of": ["is", "not set"],
                },
            ),
            1,
        )

    def test_cancelling_without_a_reason_is_refused(self):
        """A Cancellation Reason is the only record of why a posted bill was withdrawn."""
        bill = _new_bill("2026-07-01", "2026-07-31", bill_amount=180)
        bill.insert()
        bill.submit()

        with self.assertRaisesRegex(
            frappe.ValidationError, "Cancellation Reason is mandatory"
        ):
            bill.cancel()

    def test_cancelling_with_a_reason_posts_the_offsetting_reversal_row(self):
        """The acceptance counterpart to the refusal above — on_cancel must post a mirror
        row that negates the original, or the building's cost ledger keeps a bill that
        was withdrawn."""
        bill = _new_bill("2026-08-01", "2026-08-31", bill_amount=180)
        bill.insert()
        bill.submit()

        bill.cancellation_reason = "_Test correcting a duplicate bill"
        bill.cancel()

        reversal = frappe.db.get_value(
            "Accommodation Ledger",
            {"source_doctype": "Utility Bill Entry", "source_name": bill.name, "reversal_of": ["is", "set"]},
            ["reversal_of", "total_site_cost"],
            as_dict=True,
        )
        self.assertIsNotNone(reversal)
        self.assertEqual(reversal.total_site_cost, -180)
