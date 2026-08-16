# Copyright (c) 2026, AFMCO and contributors

"""M-6: Log Settings auto-clearing for the unbounded scheduler-written DocTypes.

Occupancy Snapshot, Vehicle Utilisation Snapshot and Operational Depreciation
Snapshot grow without bound via scheduled jobs. Each controller must expose a
``clear_old_logs(days)`` staticmethod (the LogType interface run_log_clean_up
invokes) and be registered in the ``default_log_clearing_doctypes`` hook so
daily_maintenance reclaims them. The financial ledgers must NOT be registered.

Access Log already implements ``clear_old_logs`` in frappe core
(frappe/core/doctype/access_log/access_log.py) — it was never registered in
EITHER frappe's own hook or this app's, so the size-based clearing cron only
ever swept rows over 1MB and an ordinary audit row accumulated forever."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.habitat.doctype.occupancy_snapshot.occupancy_snapshot import (
    OccupancySnapshot,
)
from apex.salis.doctype.vehicle_utilisation_snapshot.vehicle_utilisation_snapshot import (
    VehicleUtilisationSnapshot,
)
from apex.habitat.doctype.operational_depreciation_snapshot.operational_depreciation_snapshot import (
    OperationalDepreciationSnapshot,
)


class TestLogClearing(FrappeTestCase):
    def test_clear_old_logs_methods_exist(self):
        """Every registered snapshot controller exposes the LogType clear_old_logs entry point."""
        for cls in (
            OccupancySnapshot,
            VehicleUtilisationSnapshot,
            OperationalDepreciationSnapshot,
        ):
            self.assertTrue(
                callable(getattr(cls, "clear_old_logs", None)),
                f"{cls.__name__} must expose a callable clear_old_logs staticmethod.",
            )

    def test_default_log_clearing_hook_registered(self):
        """The three snapshots and Access Log are registered with their retention
        windows; ledgers are not."""
        hook = frappe.get_hooks("default_log_clearing_doctypes") or {}
        for dt, retention in (
            ("Occupancy Snapshot", 365),
            ("Vehicle Utilisation Snapshot", 365),
            ("Operational Depreciation Snapshot", 730),
            ("Access Log", 90),
        ):
            self.assertIn(dt, hook, f"{dt} must be registered for log clearing.")
            self.assertEqual(int(hook[dt][-1]), retention)

        for ledger in (
            "Accommodation Ledger",
            "Fuel Consumption Ledger",
            "Rental Accrual Ledger",
        ):
            self.assertNotIn(
                ledger, hook, f"{ledger} must NOT be registered for log clearing."
            )

    def test_access_log_already_supports_clearing_and_now_gets_registered(self):
        """Frappe's own AccessLog implements the LogType interface -- the registration
        this card adds is what was missing, not a new clear_old_logs method."""
        from frappe.core.doctype.log_settings.log_settings import _supports_log_clearing

        self.assertTrue(_supports_log_clearing("Access Log"))
        hook = frappe.get_hooks("default_log_clearing_doctypes") or {}
        self.assertIn("Access Log", hook)

    def test_depreciation_snapshot_clears_submitted_with_children_keeps_drafts(self):
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

        self.assertFalse(
            frappe.db.exists("Operational Depreciation Snapshot", old_sub.name),
            "Aged submitted snapshot should be cleared.",
        )
        self.assertEqual(
            frappe.db.count("Depreciation Snapshot Item", {"parent": old_sub.name}),
            0,
            "Child rows of a cleared snapshot must be deleted (no orphans).",
        )
        self.assertTrue(
            frappe.db.exists("Operational Depreciation Snapshot", recent_sub.name),
            "Recent submitted snapshot must survive.",
        )
        self.assertTrue(
            frappe.db.exists("Operational Depreciation Snapshot", old_draft.name),
            "Aged DRAFT snapshot must be preserved (not submitted).",
        )
