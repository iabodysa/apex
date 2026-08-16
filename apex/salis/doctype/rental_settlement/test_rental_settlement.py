# Copyright (c) 2026, afmcoltd

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.doctype.rental_settlement.rental_settlement import RentalSettlement

test_dependencies = ["Salis Vehicle"]


class TestRentalSettlement(FrappeTestCase):
    def test_draft_line_amount_is_derived_from_days_and_rate(self):
        settlement = RentalSettlement(
            {
                "doctype": "Rental Settlement",
                "docstatus": 0,
                "status": "Draft",
                "requested_by": "Administrator",
                "company": "Apex Co",
                "rental_office": "Rental Office A",
                "period_month": "2026-08",
                "claimed_total": 200,
                "vehicles": [
                    {
                        "doctype": "Rental Settlement Item",
                        "vehicle": "VEH-1",
                        "days": 2,
                        "daily_rate": 100,
                    }
                ],
            }
        )

        with (
            patch("apex.salis.rental_engine.linked_accrued_total", return_value=200),
            patch("apex.salis.doctype.rental_settlement.rental_settlement.apply_vat"),
        ):
            settlement.validate()

        self.assertEqual(settlement.vehicles[0].amount, 200)
        self.assertEqual(settlement.accrued_total, 200)

    def test_submitted_line_keeps_its_historical_amount(self):
        settlement = RentalSettlement(
            {
                "doctype": "Rental Settlement",
                "docstatus": 1,
                "status": "Approved",
                "requested_by": "Administrator",
                "company": "Apex Co",
                "rental_office": "Rental Office A",
                "period_month": "2026-08",
                "claimed_total": 175,
                "vehicles": [
                    {
                        "doctype": "Rental Settlement Item",
                        "vehicle": "VEH-1",
                        "days": 2,
                        "daily_rate": 100,
                        "amount": 175,
                    }
                ],
            }
        )

        with (
            patch("apex.salis.rental_engine.linked_accrued_total", return_value=175),
            patch("apex.salis.doctype.rental_settlement.rental_settlement.apply_vat"),
        ):
            settlement.validate()

        self.assertEqual(settlement.vehicles[0].amount, 175)


class TestATypedZeroSurvives(FrappeTestCase):
    """A settlement line typed as zero and a line left blank are two different facts.

    ``validate`` must overwrite a draft line's amount only when ``_amount_was_derived``
    says it is ours to recompute (rental_settlement.py:149-164), not every draft line
    unconditionally: a row of days=3, daily_rate=100, amount=0 must save as 0, not the
    recomputed 300. Overwriting an explicit zero would make a settlement claiming nothing
    report a perfect match against the rental accrual ledger, since ``accrued_total`` would
    then read the recomputed 300 rather than the 0 the operator typed.

    The distinction was measured before it was relied on. A Currency child column is NOT NULL
    DEFAULT 0, so the stored row cannot carry it; only the incoming request can, where an
    omitted field arrives as None and a typed 0 arrives as 0.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.office = (
            frappe.get_doc(
                {
                    "doctype": "Rental Office",
                    "office_name": "_ZS " + frappe.generate_hash(length=12).upper(),
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        cls.addClassCleanup(
            frappe.delete_doc, "Rental Office", cls.office, force=True, ignore_permissions=True
        )
        cls.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": "_T ABC 1001"}, "name")

    def _settlement(self, rows, period_month="2026-05"):
        doc = frappe.get_doc(
            {
                "doctype": "Rental Settlement",
                "rental_office": self.office,
                "period_month": period_month,
                "claimed_total": 0,
            }
        )
        for row in rows:
            doc.append("vehicles", {"vehicle": self.vehicle, **row})
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(
            frappe.delete_doc, "Rental Settlement", doc.name, force=True, ignore_permissions=True
        )
        return doc

    def test_a_typed_zero_amount_is_not_recomputed(self):
        """The operator said this vehicle owes nothing. Days x rate must not overrule."""
        doc = self._settlement([{"days": 3, "daily_rate": 100, "amount": 0}])
        doc.reload()
        self.assertEqual(
            doc.vehicles[0].amount,
            0,
            "a typed 0 was overwritten with days x daily_rate",
        )

    def test_a_blank_amount_is_still_computed(self):
        """The other half: absence must keep its convenience."""
        doc = self._settlement([{"days": 3, "daily_rate": 100}])
        doc.reload()
        self.assertEqual(doc.vehicles[0].amount, 300)

    def test_a_settlement_totalling_zero_keeps_zero_and_does_not_match_the_ledger(self):
        """The defect that mattered: nothing claimed must not read as a perfect match."""
        doc = self._settlement([{"days": 3, "daily_rate": 100, "amount": 0}])
        doc.reload()
        self.assertEqual(doc.accrued_total, 0, "the settlement's own total was replaced")
        self.assertFalse(
            doc.accrued_from_ledger,
            "the ledger was substituted for a settlement that HAS rows",
        )
        self.assertEqual(
            doc.ledger_variance,
            -doc.ledger_accrued_total,
            "variance against the ledger must show the full gap, not 0",
        )

    def test_a_settlement_with_no_rows_still_falls_back_and_says_so(self):
        """The fallback is kept for the one case it was meant for, and recorded."""
        doc = self._settlement([])
        doc.reload()
        self.assertEqual(doc.accrued_total, doc.ledger_accrued_total)
        self.assertTrue(
            doc.accrued_from_ledger,
            "the substitution happened but the document does not say so",
        )

    def test_a_derived_amount_still_follows_an_edit_to_its_inputs(self):
        """The convenience the read-only field depends on survives the new rule."""
        doc = self._settlement([{"days": 3, "daily_rate": 100}])
        doc.reload()
        doc.vehicles[0].days = 5
        doc.save(ignore_permissions=True)
        doc.reload()
        self.assertEqual(doc.vehicles[0].amount, 500, "a derived line went stale after an edit")

    def test_two_settlements_cannot_claim_one_office_month(self):
        """The other way this reconciliation reads as supported when it is not: both
        settlements cross-check against the SAME unsettled accrual rows, so each reports
        a perfect match and the office is paid twice for one month."""
        self._settlement([{"days": 3, "daily_rate": 100}])

        with self.assertRaises(frappe.ValidationError):
            self._settlement([{"days": 3, "daily_rate": 100}])

    def test_a_second_settlement_for_another_month_is_allowed(self):
        """The guard is (office, period), not office."""
        self._settlement([{"days": 3, "daily_rate": 100}])
        other = self._settlement([{"days": 3, "daily_rate": 100}], period_month="2026-06")

        self.assertTrue(other.name)

    def test_a_typed_zero_survives_an_edit_to_its_inputs(self):
        """And the override survives the same round trip that re-derives its neighbour."""
        doc = self._settlement([{"days": 3, "daily_rate": 100, "amount": 0}])
        doc.reload()
        doc.vehicles[0].days = 5
        doc.save(ignore_permissions=True)
        doc.reload()
        self.assertEqual(doc.vehicles[0].amount, 0, "the operator's 0 was recomputed on re-save")
