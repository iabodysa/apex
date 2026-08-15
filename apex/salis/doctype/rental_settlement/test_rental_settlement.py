# Copyright (c) 2026, afmcoltd

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from apex.salis.doctype.rental_settlement.rental_settlement import RentalSettlement


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
