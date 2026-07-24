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
"""

from __future__ import annotations

import frappe

_DOCTYPE = "Employee Deduction Acknowledgment"
_WORKFLOW = "Employee Deduction Acknowledgment Workflow"


def execute() -> None:
    if frappe.db.exists("Workflow", _WORKFLOW):
        frappe.db.delete("Workflow", {"name": _WORKFLOW})

    if frappe.db.exists("DocType", _DOCTYPE):
        frappe.db.delete("DocField", {"parent": _DOCTYPE})
        frappe.db.delete("DocPerm", {"parent": _DOCTYPE})
        frappe.db.delete("Custom Field", {"dt": _DOCTYPE})
        frappe.db.delete("Property Setter", {"doc_type": _DOCTYPE})
        frappe.db.delete("DocType", {"name": _DOCTYPE})
        frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{_DOCTYPE}`")
        frappe.clear_cache(doctype=_DOCTYPE)

    frappe.db.commit()
