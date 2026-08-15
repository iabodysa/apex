# Copyright (c) 2026, AFMCO and contributors
"""the fleet board's CAR / MOTORCYCLE bucket must match words, not substrings.

`_sheet_for` decides which chip a vehicle sits under by looking for MOTOR, BIKE, SCOOTER
or two Arabic tokens in Vehicle Category.category_name — a free Data field an admin types.
A bare substring test files anything that happens to contain those letters inside a longer
word under MOTORCYCLE, which is the same shape as the a/c-matched-jacket defect this repo
already fixed in resident_request.py.

The tokens now match at a word boundary with a trailing `\\w*`, so plurals and compounds
still land where they belong while an unrelated word carrying the letters does not.

Plain values in, a value out — no database needed.
"""

from frappe.tests.utils import FrappeTestCase

from apex.salis.api.fleet_os_board import _sheet_for


class TestTheFleetBoardSheetBucket(FrappeTestCase):
    def test_the_real_motorcycle_names_still_bucket_as_motorcycle(self):
        for name in (
            "Motorcycle",
            "MOTORBIKE",
            "Scooter",
            "Delivery Scooters",
            "Heavy Motorcycles",
            "دباب",
            "دراجة نارية",
            "دراجات",
        ):
            with self.subTest(category=name):
                self.assertEqual(_sheet_for(name), "MOTORCYCLE")

    def test_a_word_that_merely_contains_a_token_is_not_a_motorcycle(self):
        """The defect. Each of these carries a token inside a longer word and is not a
        motorcycle; a bare substring test filed every one of them under MOTORCYCLE."""
        for name in (
            "Demotorised Trailer",
            "Turbomotor Van",
            "Minibike Transporter Truck",
            "Autobike Recovery Truck",
        ):
            with self.subTest(category=name):
                self.assertEqual(_sheet_for(name), "CAR")

    def test_ordinary_car_categories_are_unchanged(self):
        for name in ("Sedan", "SUV", "Pickup", "Bus", "سيارة", "حافلة"):
            with self.subTest(category=name):
                self.assertEqual(_sheet_for(name), "CAR")

    def test_a_blank_category_falls_back_to_car(self):
        for name in (None, "", "   "):
            with self.subTest(category=name):
                self.assertEqual(_sheet_for(name), "CAR")
