# Copyright (c) 2026, AFMCO Support Services Co. Ltd and contributors
# [#j03s5a]

import frappe
from frappe.model.document import Document


class OccupancySnapshot(Document):
    @staticmethod
    def clear_old_logs(days=None):
        """Log Settings cleanup hook. This snapshot is written one row per building
		per day by the occupancy scheduler (~3,650 rows/yr per 10 buildings), so it
		grows unboundedly. Registered in hooks ``default_log_clearing_doctypes`` and
		invoked by ``daily_maintenance`` (run_log_clean_up). It is a system-written
		time-series, not a financial ledger, so a one-year retention is safe. The
		window comes from Apex Settings ``snapshot_retention_days`` (default 365)
		when the caller does not pass ``days``."""
        from frappe.query_builder import Interval
        from frappe.query_builder.functions import Now

        from apex.apex_core.doctype.apex_settings.apex_settings import (
            effective_retention_days,
        )

        days = effective_retention_days("snapshot_retention_days", days)
        table = frappe.qb.DocType("Occupancy Snapshot")
        frappe.db.delete(table, filters=(table.modified < (Now() - Interval(days=days))))


def on_doctype_update():
    """Hard idempotency backstop: a composite UNIQUE index on ``(building,
	snapshot_date)`` so the daily one-row-per-building-per-day snapshot cannot be
	double-posted at the DB level even if ``habitat.tasks.daily_occupancy_snapshot``'s
	check-then-insert is bypassed by a race. Mirrors that job's
	``frappe.db.exists({building, snapshot_date})`` guard exactly. Guarded so
	pre-existing duplicate data logs rather than aborting migrate."""
    from apex.apex_core.utils.ledger_index import add_unique_guarded

    add_unique_guarded(
        "Occupancy Snapshot",
        ["building", "snapshot_date"],
        constraint_name="unique_acc_occ_building_date",
    )
