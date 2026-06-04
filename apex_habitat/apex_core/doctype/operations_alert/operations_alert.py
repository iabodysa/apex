"""Operations Alert controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class OperationsAlert(Document):
    def before_insert(self):
        if not self.raised_on:
            self.raised_on = now_datetime()

    @staticmethod
    def clear_old_logs(days=90):
        """Log Settings cleanup hook. Operations Alert is written daily by the
        Salis reconciliation scheduler and, once Resolved, is never deleted — so it
        grows unboundedly. Registered in hooks ``default_log_clearing_doctypes`` and
        invoked by ``daily_maintenance`` (run_log_clean_up).

        Only **Resolved** alerts are aged out: an ``Open`` or ``Acknowledged`` alert
        is still actionable and must never be purged by age. The age window uses
        ``resolved_on`` (when the alert was actually closed), falling back to
        ``modified`` for rows where it is unset. Not a financial ledger."""
        from frappe.query_builder import Interval
        from frappe.query_builder.functions import Coalesce, Now

        table = frappe.qb.DocType("Operations Alert")
        cutoff = Now() - Interval(days=days)
        frappe.db.delete(
            table,
            filters=(
                (table.status == "Resolved")
                & (Coalesce(table.resolved_on, table.modified) < cutoff)
            ),
        )
