# Copyright (c) 2026, AFMCO and contributors
"""Drop the dead Employee Deduction Acknowledgment (Mahdar Iqrar) scaffolding (A-102).

The DocType modelled a KSA-Labor-Law wage-deduction consent record, but nothing ever
read or enforced it: no controller consumed it and the Salary Deduction Policy
"require acknowledgment" flags were never wired to it. A-102 removes the dead
scaffolding and its approval Workflow. Incident-driven wage recovery is being rebuilt
natively on HRMS Employee Advance / Additional Salary in a later increment.

post_model_sync: runs after the schema sync. The is_standard JSON is already gone, so
migrate leaves an orphaned ``tabEmployee Deduction Acknowledgment`` metadata row +
backing table behind (migrate is import-only and never reconciles a deleted JSON).
The rows are removed directly (not via frappe.delete_doc) so it works on a production
site with developer_mode off — mirroring archive_logistay_v1_engine. Fully guarded:
a no-op on a fresh install or any site that never had the DocType.

NO DATA IS DESTROYED. The backing table is dropped only when it is EMPTY (the expected
case — the DocType was never wired to anything). A site that somehow captured real
consent rows keeps them verbatim: the table is renamed to a plain, non-``tab`` name so
Frappe stops treating it as a DocType table while the rows stay readable in SQL.
Recovery is being rebuilt on HRMS Employee Advance / Additional Salary, which has no
column-compatible target to repoint a free-form consent row onto, so verbatim
preservation — not a lossy conversion — is the safe migration.
"""

from __future__ import annotations

import frappe

_DOCTYPE = "Employee Deduction Acknowledgment"
_WORKFLOW = "Employee Deduction Acknowledgment Workflow"
# Deliberately NOT prefixed "tab": an archive table must never look like a DocType.
_ARCHIVE_TABLE = "archived_employee_deduction_acknowledgment_a102"


def _retire_table() -> None:
    """Drop the orphaned table when empty, otherwise preserve its rows under an
    archive name. Idempotent: a second run finds no source table and does nothing."""
    if not frappe.db.table_exists(_DOCTYPE):
        return

    rows = frappe.db.sql(f"SELECT COUNT(*) FROM `tab{_DOCTYPE}`")[0][0]
    if not rows:
        frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{_DOCTYPE}`")
        return

    # NB: frappe.db.table_exists() always prefixes "tab", so the archive table (which
    # deliberately has no such prefix) has to be looked up in the raw table list.
    if _ARCHIVE_TABLE in frappe.db.get_tables(cached=False):
        # An archive from an earlier run already holds the rows; nothing left to save.
        frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{_DOCTYPE}`")
        return

    frappe.db.sql_ddl(f"RENAME TABLE `tab{_DOCTYPE}` TO `{_ARCHIVE_TABLE}`")
    frappe.logger().info(
        f"drop_employee_deduction_acknowledgment: preserved {rows} consent row(s) in "
        f"`{_ARCHIVE_TABLE}`."
    )


def execute() -> None:
    if frappe.db.exists("Workflow", _WORKFLOW):
        frappe.db.delete("Workflow", {"name": _WORKFLOW})

    if frappe.db.exists("DocType", _DOCTYPE):
        frappe.db.delete("DocField", {"parent": _DOCTYPE})
        frappe.db.delete("DocPerm", {"parent": _DOCTYPE})
        frappe.db.delete("Custom Field", {"dt": _DOCTYPE})
        frappe.db.delete("Property Setter", {"doc_type": _DOCTYPE})
        frappe.db.delete("DocType", {"name": _DOCTYPE})
        frappe.clear_cache(doctype=_DOCTYPE)

    _retire_table()
    frappe.db.commit()
