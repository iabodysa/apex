# Copyright (c) 2026, AFMCO and contributors
"""Reset Logistay to its lean two-master foundation (Freelancer + Temporary Worker).

The v1 Logistay module shipped an over-engineered, never-operationalised billing /
timesheet / reconciliation / invoice / payroll stack plus a whole ``Logistay
Governance`` module with runtime gates on ERPNext Sales Invoice / Additional Salary.
All of that source is archived out of the app. This patch removes the ORPHANED DB
records those archived JSON/module files leave behind on a site that once had them:

  * every DocType in module ``Logistay`` EXCEPT the two surviving masters, and every
    DocType in module ``Logistay Governance`` (metadata rows + backing table dropped);
  * the orphaned Logistay engine surfaces (the ``Logistay`` workspace, the
    ``Timesheet Exception Workbench`` report, the ``TS Intake Source Workflow``);
  * the payroll Custom Fields (module ``Logistay``) injected onto stock Salary
    Slip / Additional Salary / Employee Deduction Acknowledgment / Salary Deduction
    Policy; and the ``Logistay Governance`` Module Def.

post_model_sync: runs after the schema sync so the survivors exist and are never
touched. Fully guarded by existence checks — a no-op on a fresh install or any site
that never had the v1 engine. Standard-DocType rows are removed directly (not via
frappe.delete_doc) so it works on a production site with developer_mode off. The two
survivors — ``Freelancer`` and ``Temporary Worker`` — are explicitly excluded.
"""

from __future__ import annotations

import frappe

SURVIVORS = {"Freelancer", "Temporary Worker"}


def _drop_doctype(dt: str) -> None:
    """Remove one orphaned DocType's metadata rows + backing table. Guard-free of the
    developer_mode standard-doctype delete check; safe on production."""
    if dt in SURVIVORS or not frappe.db.exists("DocType", dt):
        return
    frappe.db.delete("DocField", {"parent": dt})
    frappe.db.delete("DocPerm", {"parent": dt})
    frappe.db.delete("Custom Field", {"dt": dt})
    frappe.db.delete("Property Setter", {"doc_type": dt})
    frappe.db.delete("Singles", {"doctype": dt})
    frappe.db.delete("DocType", {"name": dt})
    frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{dt}`")
    frappe.clear_cache(doctype=dt)


def execute() -> None:
    old = [
        d for d in frappe.get_all("DocType", filters={"module": "Logistay"}, pluck="name")
        if d not in SURVIVORS
    ]
    old += frappe.get_all("DocType", filters={"module": "Logistay Governance"}, pluck="name")
    for dt in old:
        _drop_doctype(dt)

    if frappe.db.exists("Workspace", "Logistay"):
        frappe.db.delete("Workspace", {"name": "Logistay"})
        frappe.clear_cache()
    if frappe.db.exists("Report", "Timesheet Exception Workbench"):
        frappe.db.delete("Report", {"name": "Timesheet Exception Workbench"})
    if frappe.db.exists("Workflow", "TS Intake Source Workflow"):
        frappe.db.delete("Workflow", {"name": "TS Intake Source Workflow"})

    pay_fields = frappe.get_all(
        "Custom Field", filters={"module": "Logistay"}, fields=["name", "dt"]
    )
    touched = {row.dt for row in pay_fields}
    if pay_fields:
        frappe.db.delete("Custom Field", {"module": "Logistay"})
        for dt in touched:
            frappe.clear_cache(doctype=dt)

    if frappe.db.exists("Module Def", "Logistay Governance"):
        frappe.db.delete("Module Def", {"name": "Logistay Governance"})

    frappe.db.commit()
