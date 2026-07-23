# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

"""M-6: Log Settings auto-clearing for the unbounded scheduler-written DocTypes.

Operations Alert, Accommodation Occupancy Snapshot and Vehicle Utilisation
Snapshot grow without bound via scheduled jobs. Each controller must expose a
``clear_old_logs(days)`` staticmethod (the LogType interface run_log_clean_up
invokes) and be registered in the ``default_log_clearing_doctypes`` hook so
daily_maintenance reclaims them. The financial ledgers must NOT be registered."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.habitat.doctype.occupancy_snapshot.occupancy_snapshot import (
    OccupancySnapshot,
)
from apex.apex_core.doctype.operations_alert.operations_alert import OperationsAlert
from apex.salis.doctype.vehicle_utilisation_snapshot.vehicle_utilisation_snapshot import (
    VehicleUtilisationSnapshot,
)
from apex.habitat.doctype.operational_depreciation_snapshot.operational_depreciation_snapshot import (
    OperationalDepreciationSnapshot,
)


class TestLogClearing(FrappeTestCase):
    def test_clear_old_logs_methods_exist(self):
        # [#pysfr6]
        for cls in (
            OperationsAlert,
            OccupancySnapshot,
            VehicleUtilisationSnapshot,
            OperationalDepreciationSnapshot,
        ):
            self.assertTrue(
                callable(getattr(cls, "clear_old_logs", None)),
                f"{cls.__name__} must expose a callable clear_old_logs staticmethod.",
            )

    def test_default_log_clearing_hook_registered(self):
        hook = frappe.get_hooks("default_log_clearing_doctypes") or {}
        for dt, retention in (
            ("Operations Alert", 90),
            ("Occupancy Snapshot", 365),
            ("Vehicle Utilisation Snapshot", 365),
            ("Operational Depreciation Snapshot", 730),
        ):
            self.assertIn(dt, hook, f"{dt} must be registered for log clearing.")
            self.assertEqual(int(hook[dt][-1]), retention)

        # [#1jshup]
        for ledger in (
            "Accommodation Ledger",
            "Fuel Consumption Ledger",
            "Rental Accrual Ledger",
        ):
            self.assertNotIn(
                ledger, hook, f"{ledger} must NOT be registered for log clearing."
            )

    def test_clear_old_logs_deletes_only_aged_rows(self):
        # [#5edkg6]
        marker = frappe.generate_hash(length=12)
        old = frappe.get_doc({
            "doctype": "Operations Alert",
            "alert_type": "Idle Vehicle",
            "severity": "Info",
            "status": "Resolved",
            "message": f"OLD-{marker}",
        }).insert(ignore_permissions=True)
        aged_open = frappe.get_doc({
            "doctype": "Operations Alert",
            "alert_type": "Idle Vehicle",
            "severity": "Info",
            "status": "Open",
            "message": f"OLDOPEN-{marker}",
        }).insert(ignore_permissions=True)
        fresh = frappe.get_doc({
            "doctype": "Operations Alert",
            "alert_type": "Idle Vehicle",
            "severity": "Info",
            "status": "Resolved",
            "message": f"NEW-{marker}",
        }).insert(ignore_permissions=True)

        # [#rmwtxu]
        for name in (old.name, aged_open.name):
            frappe.db.sql(
                "update `tabOperations Alert` set modified=%s where name=%s",
                (add_days(today(), -200), name),
            )

        OperationsAlert.clear_old_logs(days=90)

        self.assertFalse(
            frappe.db.exists("Operations Alert", old.name),
            "Aged Resolved Operations Alert should be cleared.",
        )
        self.assertTrue(
            frappe.db.exists("Operations Alert", aged_open.name),
            "Aged but still-Open Operations Alert must be kept (still actionable).",
        )
        self.assertTrue(
            frappe.db.exists("Operations Alert", fresh.name),
            "Fresh Resolved Operations Alert must survive clearing.",
        )

    def test_depreciation_snapshot_clears_submitted_with_children_keeps_drafts(self):
        # [#1qw342]
        marker = frappe.generate_hash(length=12)

        def make(suffix):
            doc = frappe.get_doc({
                "doctype": "Operational Depreciation Snapshot",
                "naming_series": "DEP-SNAP-.YYYY.-.####",
                "snapshot_date": today(),
                "building": f"QA-{marker}-{suffix}",
                "items": [{
                    "doctype": "Depreciation Snapshot Item",
                    "article": f"ART-{marker}-{suffix}",
                    "original_cost": 200,
                }],
            })
            doc.insert(ignore_permissions=True, ignore_links=True)
            return doc

        old_sub = make("oldsub")
        recent_sub = make("recentsub")
        old_draft = make("olddraft")

        # [#5vsgd7]
        for name in (old_sub.name, recent_sub.name):
            frappe.db.set_value(
                "Operational Depreciation Snapshot", name, "docstatus", 1, update_modified=False
            )
        for name in (old_sub.name, old_draft.name):
            frappe.db.sql(
                "update `tabOperational Depreciation Snapshot` set modified=%s where name=%s",
                (add_days(today(), -800), name),
            )

        OperationalDepreciationSnapshot.clear_old_logs(days=730)

        # [#h2um2i]
        self.assertFalse(
            frappe.db.exists("Operational Depreciation Snapshot", old_sub.name),
            "Aged submitted snapshot should be cleared.",
        )
        self.assertEqual(
            frappe.db.count("Depreciation Snapshot Item", {"parent": old_sub.name}),
            0,
            "Child rows of a cleared snapshot must be deleted (no orphans).",
        )
        # [#3a3nup]
        self.assertTrue(
            frappe.db.exists("Operational Depreciation Snapshot", recent_sub.name),
            "Recent submitted snapshot must survive.",
        )
        self.assertTrue(
            frappe.db.exists("Operational Depreciation Snapshot", old_draft.name),
            "Aged DRAFT snapshot must be preserved (not submitted).",
        )
