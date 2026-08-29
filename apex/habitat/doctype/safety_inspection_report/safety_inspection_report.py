# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.model.document import Document

from apex.habitat.utils.finding_fanout import fan_out_findings

_FINDING_TABLES = ("safety_findings", "maintenance_findings")


class SafetyInspectionReport(Document):
    def on_submit(self):
        self.generate_maintenance_requests()

    def on_cancel(self):
        for table_fieldname in _FINDING_TABLES:
            for finding in self.get(table_fieldname) or []:
                self._reverse_generated_request(finding.get("generated_maintenance_request"))

    def _reverse_generated_request(self, mr_name: str):
        if not mr_name or not frappe.db.exists("Maintenance Request", mr_name):
            return
        docstatus = frappe.db.get_value("Maintenance Request", mr_name, "docstatus")
        if docstatus == 0:
            frappe.delete_doc("Maintenance Request", mr_name)
        else:
            frappe.db.set_value("Maintenance Request", mr_name, "source_inspection", None)

    def generate_maintenance_requests(self):
        if self.safety_section_clear:
            return

        for table_fieldname in _FINDING_TABLES:
            rows = self.get(table_fieldname) or []
            for mr_name in fan_out_findings(rows, self):
                self._surface(mr_name)
            for finding in rows:
                self._ensure_surfaced(finding.get("generated_maintenance_request"))

    def _surface(self, mr_name: str):
        issue_type = frappe.db.get_value("Maintenance Request", mr_name, "issue_type")
        child = self.append("linked_maintenance_requests", {
            "maintenance_request": mr_name,
            "issue_type": issue_type,
            "status": "Open",
        })
        child.db_insert()

    def _ensure_surfaced(self, mr_name: str):
        if not mr_name:
            return
        for row in self.get("linked_maintenance_requests") or []:
            if row.maintenance_request == mr_name:
                return
        self._surface(mr_name)
