# Copyright (c) 2026, AFMCO and contributors

import frappe
from frappe.model.document import Document


class VehicleUtilisationSnapshot(Document):
    @staticmethod
    def clear_old_logs(days=None):
        """Log Settings cleanup hook. This snapshot is written one row per active
		vehicle per week by the utilisation scheduler, so it grows unboundedly.
		Registered in hooks ``default_log_clearing_doctypes`` and invoked by
		``daily_maintenance`` (run_log_clean_up). It is a system-written time-series,
		not a financial ledger, so a one-year retention is safe. The window comes
		from Apex Settings ``snapshot_retention_days`` (default 365) when the caller
		does not pass ``days``."""
        from frappe.query_builder import Interval
        from frappe.query_builder.functions import Now

        from apex.apex_core.doctype.apex_settings.apex_settings import (
            effective_retention_days,
        )

        days = effective_retention_days("snapshot_retention_days", days)
        table = frappe.qb.DocType("Vehicle Utilisation Snapshot")
        frappe.db.delete(table, filters=(table.modified < (Now() - Interval(days=days))))


def on_doctype_update():
    """Hard idempotency backstop: a composite UNIQUE index on (vehicle,
	snapshot_date) so the weekly one-row-per-vehicle-per-date snapshot cannot be
	double-posted at the DB level even if the engine's check-then-insert is
	bypassed by a race. Created/kept in sync on migrate via Frappe's
	on_doctype_update hook. Guarded so pre-existing duplicate data logs rather
	than aborting migrate."""
    from apex.apex_core.utils.ledger_index import add_unique_guarded

    add_unique_guarded(
        "Vehicle Utilisation Snapshot",
        ["vehicle", "snapshot_date"],
        constraint_name="unique_vus_vehicle_date",
    )
