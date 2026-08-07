# Copyright (c) 2026, afmcoltd
import frappe
from frappe.utils import now_datetime

READER_RECORDS = [
    ("Notification", "Apex Core - Operations Alert Critical"),
    ("Notification", "Salis - Workshop Overstay"),
    ("Number Card", "Unresolved Alerts"),
    ("Number Card", "Median Alert Resolve Days"),
    ("Dashboard Chart", "Open Alerts by Type"),
]


def execute():
    """Resolves open Operations Alert records, deletes its readers, and drops the retired DocType."""
    if frappe.db.table_exists("Operations Alert"):
        frappe.db.sql(
            """update `tabOperations Alert`
               set status = 'Resolved',
                   resolved_on = %(now)s,
                   resolution_note = 'Retired with the alert system',
                   modified = %(now)s
               where status in ('Open', 'Acknowledged')""",
            {"now": now_datetime()},
        )
    for doctype, name in READER_RECORDS:
        frappe.delete_doc(doctype, name, ignore_missing=True, force=True)
    frappe.delete_doc("DocType", "Operations Alert", ignore_missing=True, force=True)
    if frappe.db.table_exists("Operations Alert"):
        frappe.db.sql_ddl("drop table `tabOperations Alert`")
