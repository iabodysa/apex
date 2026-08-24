# Copyright (c) 2026, afmcoltd

import frappe
from frappe.model.document import Document
from frappe.query_builder import Interval
from frappe.query_builder.functions import Now

from apex.apex_core.doctype.habitat_settings.habitat_settings import effective_retention_days
from apex.apex_core.utils.ledger_index import add_unique_guarded


class OccupancySnapshot(Document):
    @staticmethod
    def clear_old_logs(days=None):
        days = effective_retention_days("snapshot_retention_days", days)
        table = frappe.qb.DocType("Occupancy Snapshot")
        frappe.db.delete(table, filters=(table.modified < (Now() - Interval(days=days))))


def on_doctype_update():
    add_unique_guarded(
        "Occupancy Snapshot",
        ["building", "snapshot_date"],
        constraint_name="unique_acc_occ_building_date",
    )
