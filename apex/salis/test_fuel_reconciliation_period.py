# Copyright (c) 2026, AFMCO and contributors
"""The monthly fuel reconciliation has to reconcile the month that closed.

``monthly_fuel_reconciliation`` is registered only under ``scheduler_events["monthly"]``,
which Frappe maps to cron ``0 0 1 * *``. It read "this month", so its one firing instant
was midnight on the 1st — when the month it was looking at was minutes old and its
Fuel Consumption Ledger was empty, because ``accrue_fuel_consumption`` is daily. Every
allocation was compared against ~0 litres, no breach was ever found, and the fuel-overage
alert had never fired at all.

The second case is the half that makes the first one hold: the drain used to live in the
DAILY ``reconcile_operations_alerts`` and to key off the current month too. Anchoring the
queuer on the closed month without moving the drain would have queued a breach at 00:00
on the 1st and closed it again the same day.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, getdate, today

from apex.salis.fuel_engine import _period_month, monthly_fuel_reconciliation

test_dependencies = ["Salis Vehicle"]


class TestFuelReconciliationPeriod(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.closed_month = _period_month(add_months(getdate(today()), -1))
        self.open_month = _period_month(getdate(today()))
        self.vehicle = self._vehicle()

    def _vehicle(self):
        doc = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": "_FR " + frappe.generate_hash(length=12).upper(),
                "status": "Active",
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(
            frappe.delete_doc, "Salis Vehicle", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    def _quota(self, period_month, monthly_litres=100.0):
        doc = frappe.get_doc(
            {
                "doctype": "Fuel Quota",
                "vehicle": self.vehicle,
                "period_month": period_month,
                "monthly_litres": monthly_litres,
                "status": "Active",
            }
        )
        doc.insert(ignore_permissions=True)
        doc.submit()
        self.addCleanup(self._drop, "Fuel Quota", doc.name)
        return doc.name

    def _consumption(self, period_month, litres):
        doc = frappe.get_doc(
            {
                "doctype": "Fuel Consumption Ledger",
                "vehicle": self.vehicle,
                "period_month": period_month,
                "litres": litres,
                "source_type": "Fuel Daily Log",
                "source_name": frappe.generate_hash(length=12),
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(self._drop, "Fuel Consumption Ledger", doc.name)
        return doc.name

    @staticmethod
    def _drop(doctype, name):
        doc = frappe.get_doc(doctype, name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

    def _run(self):
        """Run the real job with only the queue write stubbed, and report what it queued."""
        with (
            patch("apex.salis.tasks.common._queue_document") as queue,
            patch("apex.salis.tasks.common._reconcile_queue") as drain,
        ):
            monthly_fuel_reconciliation()
        queued = {call.args[1] for call in queue.call_args_list if call.args[0] == "Fuel Quota"}
        return queued, drain

    def test_a_breach_in_the_closed_month_is_queued(self):
        """The job's only firing instant is 00:00 on the 1st; this is the month it sees."""
        quota = self._quota(self.closed_month)
        self._consumption(self.closed_month, 500.0)

        queued, _drain = self._run()

        self.assertIn(quota, queued, "the month that closed was never reconciled")

    def test_the_month_that_has_just_started_is_not_the_one_reconciled(self):
        """The defect, stated as its own case: a fresh month has no ledger rows yet, so
        anchoring there means no allocation can ever breach."""
        quota = self._quota(self.open_month)
        self._consumption(self.open_month, 500.0)

        queued, _drain = self._run()

        self.assertNotIn(
            quota, queued, "the job reconciled a month whose ledger has not been written yet"
        )

    def test_the_job_drains_the_queue_it_alone_fills(self):
        """The drain has to sit beside the queuer, or a daily job on a different month
        closes what this one just raised."""
        quota = self._quota(self.closed_month)
        self._consumption(self.closed_month, 500.0)

        _queued, drain = self._run()

        drain.assert_called_once()
        doctype, still_breached = drain.call_args.args
        self.assertEqual(doctype, "Fuel Quota")
        self.assertIn(quota, still_breached)

    def test_the_daily_reconciler_no_longer_touches_fuel_quota(self):
        """Its own docstring named Fuel Quota as one of the three it drains. If it still
        drains it on the current month, the case above passes and production still loses
        the alert the next morning."""
        from apex.salis.tasks import alerts

        with patch.object(alerts, "_reconcile_queue", return_value=0) as drain:
            alerts.reconcile_operations_alerts()

        self.assertNotIn(
            "Fuel Quota",
            {call.args[0] for call in drain.call_args_list},
            "the daily drain still closes a queue it does not fill",
        )
