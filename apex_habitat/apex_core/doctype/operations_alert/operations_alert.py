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
        Salis reconciliation scheduler and resolved-but-never-deleted, so it grows
        unboundedly. Registered in hooks ``default_log_clearing_doctypes`` and
        invoked by ``daily_maintenance`` (run_log_clean_up). Not a financial
        ledger — safe to age out."""
        from frappe.query_builder import Interval
        from frappe.query_builder.functions import Now

        table = frappe.qb.DocType("Operations Alert")
        frappe.db.delete(table, filters=(table.modified < (Now() - Interval(days=days))))
