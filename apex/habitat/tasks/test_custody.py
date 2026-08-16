# Copyright (c) 2026, AFMCO and contributors
"""Tests for the consumable custody expiry watch's age-in-months calculation.

A held position is over-age once its age in whole months reaches the article's
own ``consumable_lifespan_months``. The docstring promises a day-of-month
correction (an article held since the 20th is not yet a full month old on the
15th of the following month), so this pins that branch directly: the same
"held since" date reads as under-lifespan or over-lifespan purely on which side
of today's day-of-month it falls, with the lifespan held fixed. Ledger rows are
inserted with ``ignore_links`` (the doctype's own smoke-test pattern) so the
employee/building tokens need not be real masters; the article is real because
the pass INNER JOINs Custody Article for its lifespan.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, getdate, today

from apex.habitat.tasks.custody import consumable_custody_expiry_watch


def _h(n=10):
    return frappe.generate_hash(length=n).upper()


class TestConsumableExpiryDayOfMonthCorrection(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.category = frappe.get_doc(
            {"doctype": "Custody Asset Category", "category_name": "Cat " + _h()}
        ).insert(ignore_permissions=True)
        self.employee = "EMP-" + _h()
        self.building = "BLDG-" + _h()
        self._notified = []
        self._names = []

    def tearDown(self):
        for doctype, name in reversed(self._names):
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)

    def _article(self, lifespan_months):
        doc = frappe.get_doc(
            {
                "doctype": "Custody Article",
                "article_name": "Art " + _h(),
                "category": self.category.name,
                "consumable_lifespan_months": lifespan_months,
            }
        ).insert(ignore_permissions=True)
        self._names.append(("Custody Article", doc.name))
        return doc.name

    def _hold(self, article, held_since):
        doc = frappe.get_doc(
            {
                "doctype": "Accommodation Stock Ledger",
                "naming_series": "ACC-SLE-.YYYY.-.######",
                "posting_date": held_since,
                "item_type": "Custody Article",
                "item": article,
                "item_name": "held",
                "uom": "Nos",
                "signed_qty": 1,
                "building": self.building,
                "employee": self.employee,
                "is_cancelled": 0,
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        self._names.append(("Accommodation Stock Ledger", doc.name))

    def _run_and_capture_flags(self):
        """Runs the watch and returns whether the notify helper fired."""
        with patch("apex.habitat.tasks.custody._notify_role_system") as notify:
            consumable_custody_expiry_watch()
        return notify.called

    def test_a_position_held_exactly_the_lifespan_and_past_the_day_of_month_is_flagged(self):
        """Held on day D two months ago; today is on/after day D -> 2 full months old."""
        held_since = add_months(getdate(today()), -2)
        article = self._article(lifespan_months=2)
        self._hold(article, held_since)

        self.assertTrue(self._run_and_capture_flags())

    def test_a_position_not_yet_past_the_day_of_month_is_one_month_short(self):
        """Held one day AFTER the anchor day -> today's day-of-month has not yet
        reached it, so the age is lifespan-1 whole months, not lifespan."""
        held_since = add_days(add_months(getdate(today()), -2), 1)
        article = self._article(lifespan_months=2)
        self._hold(article, held_since)

        self.assertFalse(self._run_and_capture_flags())
