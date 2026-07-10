# Copyright (c) 2026, AFMCO and contributors
"""Row-relative card: counts buildings whose occupancy exceeds their OWN
threshold (zero/unset falls back to the 120 default). Stored Percent columns are
forced via db.set_value (validate would recompute); asserts are delta-based so
they don't collide with pre-existing rows."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.dashboard import (
    get_buildings_over_threshold as _get_buildings_over_threshold,
)


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


# Card returns the {value: n, ...df} dict contract; unwrap to the count here.
def get_buildings_over_threshold():
    return _get_buildings_over_threshold()["value"]


class TestBuildingsOverThreshold(FrappeTestCase):
    def setUp(self):
        self._names = []
        self.baseline = get_buildings_over_threshold()

    def _building(self, occupancy, threshold):
        """Insert a building and force the two stored Percent columns directly."""
        doc = frappe.get_doc({
            "doctype": "Building",
            "building_name": "BLDG-" + _h(),
        })
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.set_value(
            "Building",
            doc.name,
            {"occupancy_percent": occupancy, "over_capacity_threshold_percent": threshold},
            update_modified=False,
        )
        self._names.append(doc.name)
        return doc.name

    def tearDown(self):
        for name in self._names:
            frappe.delete_doc("Building", name, force=True,
                              ignore_permissions=True)

    def test_counts_only_buildings_over_their_own_threshold(self):
        # Over its own threshold (130 > 120) -> counted.
        self._building(occupancy=130, threshold=120)
        # Exactly at threshold (120 == 120) -> NOT counted (strict greater-than).
        self._building(occupancy=120, threshold=120)
        # Under its own threshold (90 < 120) -> NOT counted.
        self._building(occupancy=90, threshold=120)
        # A high per-row threshold suppresses the count even when occupied (110 < 150).
        self._building(occupancy=110, threshold=150)

        delta = get_buildings_over_threshold() - self.baseline
        self.assertEqual(delta, 1,
                         "only the building strictly over its own threshold is counted")

    def test_unset_threshold_falls_back_to_default_not_zero(self):
        # Threshold 0 must mean 'use the default 120', NOT 'over 0%'. At 50%
        # occupancy with a 0 threshold the building is below the 120 default.
        self._building(occupancy=50, threshold=0)
        self.assertEqual(get_buildings_over_threshold() - self.baseline, 0,
                         "a 0/unset threshold falls back to 120 and is not over")

        # Above the default fallback (130 > 120) it IS counted.
        self._building(occupancy=130, threshold=0)
        self.assertEqual(get_buildings_over_threshold() - self.baseline, 1,
                         "occupancy over the 120 default counts when threshold unset")

    def test_returns_number_card_dict_contract(self):
        res = _get_buildings_over_threshold()
        # Custom Number Card contract: {value: <number>, ...df}.
        self.assertIsInstance(res, dict, "Custom Number Card returns a dict, not a scalar")
        self.assertIn("value", res, "the number must live under the 'value' key")
        self.assertIsInstance(res["value"], int)
        self.assertGreaterEqual(res["value"], 0)
        self.assertEqual(res.get("fieldtype"), "Int")
