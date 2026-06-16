"""Safety Inspection Report controller.

On submit, the report fans out: each ACTIONABLE finding (one carrying an
issue_type, a room, and not already resolved) spawns one Maintenance Request,
the report's existing source_inspection back-link is stamped on the ticket, and
the generated request is surfaced in the read-only linked_maintenance_requests
table. The fan-out mirrors the conversion pattern in
accommodation_resident_request.convert_request (frappe.new_doc + insert +
back-link stamp) rather than get_mapped_doc, because one report spawns N tickets
across two finding tables — a one-source-to-one-target mapper does not fit.

The fan-out is implemented as the Document.on_submit class method (Frappe calls
it natively on submit; no hooks.py doc_events entry is needed), keeping every
change inside this DocType.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

# [#pdq7ji]
_FINDING_TABLES = ("safety_findings", "maintenance_findings")


class SafetyInspectionReport(Document):
    def on_submit(self):
        self.generate_maintenance_requests()

    # [#7usew1]
    # [#t8xr0s]
    # [#7usew1]
    def generate_maintenance_requests(self):
        """Create one Maintenance Request per actionable finding and surface it.

        Idempotent by design:
          * a finding already carrying a live generated_maintenance_request is
            skipped (covers re-submit-after-amend, where the back-link is copied
            forward, and any defensive re-run);
          * only actionable findings spawn a ticket (see _is_actionable);
          * the report is short-circuited entirely when safety_section_clear is
            set (the inspector declared no issues).
        """
        if self.safety_section_clear:
            return

        for table_fieldname in _FINDING_TABLES:
            for finding in self.get(table_fieldname) or []:
                if not _is_actionable(finding):
                    continue
                if _already_linked(finding):
                    self._ensure_surfaced(finding.generated_maintenance_request)
                    continue
                mr_name = self._spawn_request(finding)
                # [#3yfjbk]
                # [#nv82oa]
                finding.db_set("generated_maintenance_request", mr_name)
                self._surface(mr_name)

    def _spawn_request(self, finding) -> str:
        """Build, insert, and return the name of the MR for one finding.

        Maps room / issue_type / priority / building and stamps source_inspection
        (the report's existing back-link field on Maintenance Request)."""
        mr = frappe.new_doc("Maintenance Request")
        mr.building = self.building
        mr.room = finding.room
        mr.issue_type = finding.issue_type
        mr.priority = finding.priority or "Medium"
        mr.issue_description = finding.description or _(
            "Auto-generated from safety inspection {0}"
        ).format(self.name)
        mr.reported_by = self.inspector or frappe.session.user
        mr.status = "Open"
        mr.source_inspection = self.name
        # [#biju55]
        # [#gek2ue]
        mr.insert(ignore_permissions=True)  # audit-ok
        return mr.name

    def _surface(self, mr_name: str):
        """Append the generated MR to the read-only surfacing table (in memory;
        persisted by the direct db write below so the submitted parent's modified
        stamp is not disturbed)."""
        issue_type = frappe.db.get_value("Maintenance Request", mr_name, "issue_type")
        child = self.append("linked_maintenance_requests", {
            "maintenance_request": mr_name,
            "issue_type": issue_type,
            "status": "Open",
        })
        child.db_insert()

    def _ensure_surfaced(self, mr_name: str):
        """Make sure an already-linked finding's MR is present in the surfacing
        table exactly once (covers a partially-completed earlier run)."""
        if not mr_name:
            return
        for row in self.get("linked_maintenance_requests") or []:
            if row.maintenance_request == mr_name:
                return
        self._surface(mr_name)


def _is_actionable(finding) -> bool:
    """A finding warrants a ticket when it names an issue_type and a room and is
    not already resolved. issue_type is the explicit 'this needs maintenance'
    signal; a resolved finding needs no new ticket."""
    if not finding.get("issue_type"):
        return False
    if not finding.get("room"):
        return False
    if (finding.get("status") or "") == "Resolved":
        return False
    return True


def _already_linked(finding) -> bool:
    """True only when the recorded back-link points at a Maintenance Request that
    still exists — a dangling link (target deleted) is treated as not linked so a
    fresh ticket is created."""
    mr_name = finding.get("generated_maintenance_request")
    if not mr_name:
        return False
    return bool(frappe.db.exists("Maintenance Request", mr_name))
