# Copyright (c) 2026, afmcoltd
"""Safety Inspection Report controller.

On submit, the report fans out: each ACTIONABLE finding (one carrying an
issue_type, a room, and not already resolved) spawns one Maintenance Request,
the report's source_inspection back-link is stamped on the ticket, and the
generated request is surfaced in the read-only linked_maintenance_requests
table.

The fan-out + idempotency logic itself now lives in the shared
habitat.utils.finding_fanout helper, so this report and the live Safety Task
Execution path share one implementation (DRY). This controller keeps only the
report-specific concerns: the safety_section_clear short-circuit, iterating the
two finding tables, and surfacing each generated ticket in the read-only
linked_maintenance_requests table.

The fan-out is implemented as the Document.on_submit class method (Frappe calls
it natively on submit; no hooks.py doc_events entry is needed).
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document

from apex.habitat.utils.finding_fanout import fan_out_findings

_FINDING_TABLES = ("safety_findings", "maintenance_findings")


class SafetyInspectionReport(Document):
    def on_submit(self):
        """Fans out each actionable finding into a Maintenance Request when the report is submitted."""
        self.generate_maintenance_requests()

    def on_cancel(self):
        """Reverse the on_submit fan-out: a cancelled report must not leave its
        auto-spawned Maintenance Requests carrying a stale source_inspection
        back-link. A still-draft generated ticket is a pure side-effect and is
        deleted; a ticket already picked up (submitted) is left for the team and
        only its dangling back-link is cleared. Native class method — Frappe fires
        it on cancel; no hooks.py doc_event needed."""
        for table_fieldname in _FINDING_TABLES:
            for finding in self.get(table_fieldname) or []:
                self._reverse_generated_request(finding.get("generated_maintenance_request"))

    def _reverse_generated_request(self, mr_name: str):
        """Deletes a still-draft generated Maintenance Request or clears its source-inspection link."""
        if not mr_name or not frappe.db.exists("Maintenance Request", mr_name):
            return
        docstatus = frappe.db.get_value("Maintenance Request", mr_name, "docstatus")
        if docstatus == 0:
            # audit-ok
            frappe.delete_doc("Maintenance Request", mr_name, ignore_permissions=True)  # audit-ok
        else:
            frappe.db.set_value("Maintenance Request", mr_name, "source_inspection", None)

    def generate_maintenance_requests(self):
        """Fan out each actionable finding to one Maintenance Request and surface it.

        Idempotent by design (delegated to finding_fanout):
          * a finding already carrying a live generated_maintenance_request is
            skipped (covers re-submit-after-amend and any defensive re-run);
          * only actionable findings spawn a ticket;
          * the report is short-circuited entirely when safety_section_clear is
            set (the inspector declared no issues).
        """
        if self.safety_section_clear:
            return

        for table_fieldname in _FINDING_TABLES:
            rows = self.get(table_fieldname) or []
            for mr_name in fan_out_findings(rows, self):
                self._surface(mr_name)
            for finding in rows:
                self._ensure_surfaced(finding.get("generated_maintenance_request"))

    def _surface(self, mr_name: str):
        """Append the generated MR to the read-only surfacing table.

        Persisted by a direct db write so the submitted parent's modified stamp
        is not disturbed."""
        issue_type = frappe.db.get_value("Maintenance Request", mr_name, "issue_type")
        child = self.append("linked_maintenance_requests", {
            "maintenance_request": mr_name,
            "issue_type": issue_type,
            "status": "Open",
        })
        child.db_insert()

    def _ensure_surfaced(self, mr_name: str):
        """Make sure an already-linked finding's MR is present in the surfacing
        table exactly once."""
        if not mr_name:
            return
        for row in self.get("linked_maintenance_requests") or []:
            if row.maintenance_request == mr_name:
                return
        self._surface(mr_name)
