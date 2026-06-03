# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

"""M-6: Log Settings auto-clearing for the unbounded scheduler-written DocTypes.

Operations Alert, Accommodation Occupancy Snapshot and Vehicle Utilisation
Snapshot grow without bound via scheduled jobs. Each controller must expose a
``clear_old_logs(days)`` staticmethod (the LogType interface run_log_clean_up
invokes) and be registered in the ``default_log_clearing_doctypes`` hook so
daily_maintenance reclaims them. The financial ledgers must NOT be registered."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex_habitat.habitat.doctype.accommodation_occupancy_snapshot.accommodation_occupancy_snapshot import (
    AccommodationOccupancySnapshot,
)
from apex_habitat.apex_core.doctype.operations_alert.operations_alert import OperationsAlert
from apex_habitat.salis.doctype.vehicle_utilisation_snapshot.vehicle_utilisation_snapshot import (
    VehicleUtilisationSnapshot,
)
from apex_habitat.habitat.doctype.non_financial_depreciation_snapshot.non_financial_depreciation_snapshot import (
    NonFinancialDepreciationSnapshot,
)


class TestLogClearing(FrappeTestCase):
    def test_clear_old_logs_methods_exist(self):
        # Each controller exposes the LogType clear_old_logs interface so
        # run_log_clean_up can invoke it.
        for cls in (
            OperationsAlert,
            AccommodationOccupancySnapshot,
            VehicleUtilisationSnapshot,
            NonFinancialDepreciationSnapshot,
        ):
            self.assertTrue(
                callable(getattr(cls, "clear_old_logs", None)),
                f"{cls.__name__} must expose a callable clear_old_logs staticmethod.",
            )

    def test_default_log_clearing_hook_registered(self):
        hook = frappe.get_hooks("default_log_clearing_doctypes") or {}
        for dt, retention in (
            ("Operations Alert", 90),
            ("Accommodation Occupancy Snapshot", 365),
            ("Vehicle Utilisation Snapshot", 365),
            ("Non-Financial Depreciation Snapshot", 730),
        ):
            self.assertIn(dt, hook, f"{dt} must be registered for log clearing.")
            self.assertEqual(int(hook[dt][-1]), retention)

        # The financial ledgers must NOT be auto-cleared (audit significance).
        for ledger in (
            "Accommodation Ledger",
            "Fuel Consumption Ledger",
            "Rental Accrual Ledger",
        ):
            self.assertNotIn(
                ledger, hook, f"{ledger} must NOT be registered for log clearing."
            )

    def test_clear_old_logs_deletes_only_aged_rows(self):
        # Operations Alert has no mandatory Link, so it is the cleanest proof that
        # clear_old_logs deletes rows older than the retention and keeps fresh ones.
        marker = frappe.generate_hash(length=8)
        old = frappe.get_doc({
            "doctype": "Operations Alert",
            "alert_type": "Idle Vehicle",
            "severity": "Info",
            "message": f"OLD-{marker}",
        }).insert(ignore_permissions=True)
        fresh = frappe.get_doc({
            "doctype": "Operations Alert",
            "alert_type": "Idle Vehicle",
            "severity": "Info",
            "message": f"NEW-{marker}",
        }).insert(ignore_permissions=True)

        # Backdate the old row's modified well past the retention window.
        frappe.db.sql(
            "update `tabOperations Alert` set modified=%s where name=%s",
            (add_days(today(), -200), old.name),
        )

        OperationsAlert.clear_old_logs(days=90)

        self.assertFalse(
            frappe.db.exists("Operations Alert", old.name),
            "Aged Operations Alert should be cleared.",
        )
        self.assertTrue(
            frappe.db.exists("Operations Alert", fresh.name),
            "Fresh Operations Alert must survive clearing.",
        )

    def test_depreciation_snapshot_clears_submitted_with_children_keeps_drafts(self):
        # The Depreciation Snapshot has a child table AND is submittable, so its
        # clear_old_logs must (a) purge only SUBMITTED rows older than retention,
        # (b) delete their child items (frappe.db.delete does not cascade), and
        # (c) leave drafts alone.
        marker = frappe.generate_hash(length=8)

        def make(suffix):
            doc = frappe.get_doc({
                "doctype": "Non-Financial Depreciation Snapshot",
                "naming_series": "DEP-SNAP-.YYYY.-.####",
                "snapshot_date": today(),
                "building": f"QA-{marker}-{suffix}",
                "items": [{
                    "doctype": "Depreciation Snapshot Item",
                    "article": f"ART-{marker}-{suffix}",
                    "original_cost_sar": 200,
                }],
            })
            doc.insert(ignore_permissions=True, ignore_links=True)
            return doc

        old_sub = make("oldsub")
        recent_sub = make("recentsub")
        old_draft = make("olddraft")

        # Mark the two "submitted" rows docstatus=1 (bypass submit's link checks),
        # then backdate the two "old" rows well past the 730-day window.
        for name in (old_sub.name, recent_sub.name):
            frappe.db.set_value(
                "Non-Financial Depreciation Snapshot", name, "docstatus", 1, update_modified=False
            )
        for name in (old_sub.name, old_draft.name):
            frappe.db.sql(
                "update `tabNon-Financial Depreciation Snapshot` set modified=%s where name=%s",
                (add_days(today(), -800), name),
            )

        NonFinancialDepreciationSnapshot.clear_old_logs(days=730)

        # Aged SUBMITTED snapshot and its child items are gone (no orphans).
        self.assertFalse(
            frappe.db.exists("Non-Financial Depreciation Snapshot", old_sub.name),
            "Aged submitted snapshot should be cleared.",
        )
        self.assertEqual(
            frappe.db.count("Depreciation Snapshot Item", {"parent": old_sub.name}),
            0,
            "Child rows of a cleared snapshot must be deleted (no orphans).",
        )
        # Recent submitted survives; aged DRAFT survives (only docstatus=1 is purged).
        self.assertTrue(
            frappe.db.exists("Non-Financial Depreciation Snapshot", recent_sub.name),
            "Recent submitted snapshot must survive.",
        )
        self.assertTrue(
            frappe.db.exists("Non-Financial Depreciation Snapshot", old_draft.name),
            "Aged DRAFT snapshot must be preserved (not submitted).",
        )
