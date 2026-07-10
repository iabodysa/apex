# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Arrivals telemetry Number Card methods get_arrivals_today and
get_pending_on_manifest. Each case scopes to a unique building so the asserts are
exact regardless of pre-existing site data. Assignments are inserted directly and
forced to docstatus=1 + check_in_date via db.set_value (validate would otherwise
run the bed-lock/occupancy gates) — the same direct approach the sibling
dashboard tests use."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.habitat.api.dashboard import (
    get_arrivals_today as _get_arrivals_today,
    get_pending_on_manifest as _get_pending_on_manifest,
)


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


# Cards return the {value: n, ...df} dict contract; unwrap to the count here.
def get_arrivals_today():
    return _get_arrivals_today()["value"]


def get_pending_on_manifest():
    return _get_pending_on_manifest()["value"]


class TestDashboardArrivals(FrappeTestCase):
    def setUp(self):
        self.today = today()
        self.yesterday = add_days(self.today, -1)
        self.building = "BLDG-" + _h()
        self._assignments = []
        self._batches = []

    def _assignment(self, check_in_date, building=None):
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "party_type": "Employee",
            "party": "EMP-" + _h(),
            "employee": "EMP-" + _h(),
            "building": building or self.building,
        })
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.set_value(
            "Housing Assignment", doc.name,
            {"docstatus": 1, "check_in_date": check_in_date}, update_modified=False,
        )
        self._assignments.append(doc.name)
        return doc.name

    def _batch(self, expected_date, expected_n, building=None):
        doc = frappe.get_doc({
            "doctype": "Arrival Batch",
            "building": building or self.building,
            "expected_date": expected_date,
            "expected_workers": [
                {"worker_name": "W-" + _h(), "passport_number": "P" + _h(12)}
                for _ in range(expected_n)
            ],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self._batches.append(doc.name)
        return doc.name

    def tearDown(self):
        for name in self._assignments:
            frappe.db.set_value("Housing Assignment", name, "docstatus", 0,
                                update_modified=False)
            frappe.delete_doc("Housing Assignment", name, force=True,
                              ignore_permissions=True)
        for name in self._batches:
            frappe.delete_doc("Arrival Batch", name, force=True, ignore_permissions=True)

    # get_arrivals_today

    def test_arrivals_today_counts_only_today_submitted(self):
        """Only today's submitted check-ins are counted; yesterday's is excluded."""
        base = get_arrivals_today()
        self._assignment(self.today)
        self._assignment(self.today)
        self._assignment(self.yesterday)  # excluded: not today
        self.assertEqual(get_arrivals_today(), base + 2)

    def test_arrivals_today_ignores_draft(self):
        """A draft (docstatus=0) check-in dated today is not counted."""
        base = get_arrivals_today()
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "party_type": "Employee",
            "party": "EMP-" + _h(),
            "employee": "EMP-" + _h(),
            "building": self.building,
        })
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.set_value("Housing Assignment", doc.name, "check_in_date",
                            self.today, update_modified=False)
        self._assignments.append(doc.name)
        self.assertEqual(get_arrivals_today(), base, "draft check-in must not count")

    # get_pending_on_manifest

    def test_pending_is_expected_minus_housed(self):
        """A due manifest of 3 with 1 housed in the building on its date leaves 2
        pending, mirroring ArrivalBatch.pending_arrival_count."""
        base = get_pending_on_manifest()
        self._batch(self.yesterday, 3)
        self._assignment(self.yesterday)  # 1 housed against the manifest
        self.assertEqual(get_pending_on_manifest(), base + 2)

    def test_future_manifest_not_yet_pending(self):
        """A manifest whose expected_date is in the future is not counted yet."""
        base = get_pending_on_manifest()
        self._batch(add_days(self.today, 5), 4)
        self.assertEqual(get_pending_on_manifest(), base, "future batch excluded")

    def test_over_arrival_clamps_to_zero(self):
        """More housed than expected for one batch clamps that batch to 0 and does
        not offset another batch's shortfall (GREATEST(...,0) per batch)."""
        base = get_pending_on_manifest()
        # Batch A: expect 1, house 3 (over-arrival) -> contributes 0, not -2.
        self._batch(self.yesterday, 1)
        self._assignment(self.yesterday)
        self._assignment(self.yesterday)
        self._assignment(self.yesterday)
        # Batch B: a different building/date, expect 2, house 0 -> contributes 2.
        other_building = "BLDG-" + _h()
        self._batch(self.yesterday, 2, building=other_building)
        self.assertEqual(get_pending_on_manifest(), base + 2)

    # return-shape contract (both cards)

    def test_cards_return_number_card_dict_contract(self):
        """Both methods return the Custom Number Card {value: n, ...df} dict, not a
        bare scalar (a scalar renders but drops the format docfield)."""
        for res in (_get_arrivals_today(), _get_pending_on_manifest()):
            self.assertIsInstance(res, dict, "Custom Number Card returns a dict, not a scalar")
            self.assertIn("value", res, "the number must live under the 'value' key")
            self.assertIsInstance(res["value"], int)
            self.assertEqual(res.get("fieldtype"), "Int")
