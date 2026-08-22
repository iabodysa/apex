# Copyright (c) 2026, afmcoltd
"""What an Operational Depreciation Snapshot guarantees, asserted against the DocType
itself.

Patterned on frappe's own document lifecycle tests (``frappe/tests/test_document.py``,
``test_validate`` / ``test_update_after_submit``). Both ``validate`` and ``before_cancel``
here are module-level functions wired through ``hooks.py``'s ``doc_events`` (not methods on
the ``Document`` subclass), so they only run through the real lifecycle calls —
``insert()`` and ``cancel()`` — exercised below, never invoked directly.

Two guarantees: ``validate`` computes each asset line's book value from its policy
(falling back to original cost when a line carries none) and totals them into
``total_book_value``; ``before_cancel`` refuses to withdraw a submitted snapshot without a
stated ``cancellation_reason``.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building", "Custody Article", "Operational Depreciation Policy"]


class TestOperationalDepreciationSnapshot(FrappeTestCase):
    def test_an_item_without_a_policy_books_at_its_original_cost(self):
        """The standing fixture's own shape: a line with no policy has nothing to
        depreciate it by, so it books at cost."""
        snapshot = frappe.copy_doc(
            frappe.get_test_records("Operational Depreciation Snapshot")[0]
        )
        snapshot.insert()

        self.assertEqual(snapshot.items[0].book_value, snapshot.items[0].original_cost)
        self.assertEqual(snapshot.total_book_value, snapshot.items[0].original_cost)

    def test_a_straight_line_policy_computes_the_depreciated_book_value(self):
        """Pins the straight-line formula itself: book value = original - (depreciable /
        life) * age, floored at the residual. A wrong coefficient here silently mis-states
        every book value the Depreciation Aging report reads.

        _Test Straight Line 5yr: useful_life=5, residual_pct=10% -> residual=100,
        depreciable=900, annual=180 -> book_value = 1000 - 180*2 = 640.
        """
        article = frappe.db.get_value(
            "Custody Article", {"article_name": "_Test Blanket"}, "name"
        )
        snapshot = frappe.new_doc("Operational Depreciation Snapshot")
        snapshot.naming_series = "DEP-SNAP-.YYYY.-.####"
        snapshot.snapshot_date = "2026-03-31"
        snapshot.building = "_Test Building"
        snapshot.append(
            "items",
            {
                "article": article,
                "policy": "_Test Straight Line 5yr",
                "original_cost": 1000,
                "age_years": 2,
            },
        )
        snapshot.insert()

        self.assertEqual(snapshot.items[0].book_value, 640)
        self.assertEqual(snapshot.total_book_value, 640)

    def test_cancelling_without_a_reason_is_refused(self):
        """A Cancellation Reason is the only record of why a submitted depreciation
        snapshot was withdrawn; without this refusal it disappears silently."""
        snapshot = frappe.copy_doc(
            frappe.get_test_records("Operational Depreciation Snapshot")[0]
        )
        snapshot.snapshot_date = "2026-04-30"
        snapshot.insert()
        snapshot.submit()

        with self.assertRaisesRegex(frappe.ValidationError, "Cancellation Reason is required"):
            snapshot.cancel()

    def test_cancelling_with_a_reason_is_accepted(self):
        """The acceptance counterpart to the refusal above — a stated reason must still let
        cancellation through, or the refusal is blocking everyone rather than guarding one
        thing."""
        snapshot = frappe.copy_doc(
            frappe.get_test_records("Operational Depreciation Snapshot")[0]
        )
        snapshot.snapshot_date = "2026-05-31"
        snapshot.insert()
        snapshot.submit()

        snapshot.cancellation_reason = "_Test correcting a mis-entered original cost"
        snapshot.cancel()

        self.assertEqual(
            frappe.db.get_value(
                "Operational Depreciation Snapshot", snapshot.name, "docstatus"
            ),
            2,
        )
