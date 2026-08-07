# Copyright (c) 2026, afmcoltd
"""Safety Task Execution controller.

A live execution captures findings observed in the field. On submit it fans out
each actionable finding to one Maintenance Request via the shared
habitat.utils.finding_fanout helper, stamping source_execution on the ticket and
writing the finding's generated_maintenance_request back-link (idempotent). A
Poor / Not Done overall result additionally raises one building-scoped summary
Maintenance Request, stamped on linked_maintenance_request (also idempotent).

Validation enforces photo evidence: a FAILED outcome (Poor / Not Done) on a
catalog task flagged evidence_required must carry an Evidence Photo, and a
Security-category finding must carry one before it can drive an escalation.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.habitat.utils.finding_fanout import fan_out_findings, is_actionable

_SECURITY_CATEGORY = "security"

_REPAIR_NEEDED_STATUSES = ("Poor", "Not Done")


class SafetyTaskExecution(Document):
    def validate(self):
        """Blocks submission when required photo evidence for a failed or security finding is missing."""
        self._enforce_evidence()

    def on_submit(self):
        """Fans findings out into Maintenance Requests and raises a summary ticket for a failed execution."""
        fan_out_findings(self.findings, self)
        self._escalate_failed_execution()

    def on_cancel(self):
        """Closes any untouched, still-Open Maintenance Requests this execution raised."""
        self._retract_untouched_requests()

    def _retract_untouched_requests(self) -> None:
        """Close the tickets this execution raised that nobody has picked up.

        The tickets are found by source_execution, the back-link stamped at
        creation, so a finding edited or removed after submit cannot hide one.
        A ticket is retracted only while it is still an untouched Draft at
        status Open; once it is assigned, progressed, submitted or resolved a
        technician owns it, and cancelling the paperwork behind it must not
        reach into work that has already started."""
        frappe.db.set_value(
            "Maintenance Request",
            {"source_execution": self.name, "docstatus": 0, "status": "Open"},
            "status",
            "Closed",
        )

    def _escalate_failed_execution(self) -> None:
        """Raise ONE building-scoped Maintenance Request when the task failed.

        Fulfils the linked_maintenance_request schema promise: a Poor / Not Done
        overall result means the task itself failed and needs a repair. Distinct
        from the per-finding fan-out (which spawns room-specific tickets). The
        single linked_maintenance_request back-link makes the escalation
        idempotent — a defensive re-run never duplicates the summary ticket."""
        if self.execution_status not in _REPAIR_NEEDED_STATUSES:
            return
        if self._has_linked_request():
            return
        room = self._scope_room()
        if not room:
            return
        mr = frappe.new_doc("Maintenance Request")
        mr.building = self.building
        mr.room = room
        mr.issue_type = "Other"
        mr.priority = "High"
        mr.issue_description = _(
            "Safety task '{0}' failed on {1} (result: {2}). Repair required."
        ).format(self.task, self.execution_date, self.execution_status)
        mr.reported_by = self.executed_by or frappe.session.user
        mr.status = "Open"
        mr.source_execution = self.name
        mr.insert(ignore_permissions=True)  # audit-ok
        self.db_set("linked_maintenance_request", mr.name)

    def _has_linked_request(self) -> bool:
        """True only when linked_maintenance_request points at a live ticket; a
        dangling link (target deleted) is treated as unlinked so a fresh summary
        ticket is created."""
        mr_name = self.linked_maintenance_request
        if not mr_name:
            return False
        return bool(frappe.db.exists("Maintenance Request", mr_name))

    def _scope_room(self) -> str | None:
        """A representative room for the building-scoped summary ticket.

        Prefers a room already named on a finding (so the ticket lands on a real
        observed location); otherwise the first room of the building. Returns None
        when the building has no rooms at all."""
        for finding in self.findings or []:
            if finding.get("room"):
                return finding.get("room")
        return frappe.db.get_value(
            "Room", {"building": self.building}, "name"
        )

    def _enforce_evidence(self):
        """Throw a clear English message when required photo evidence is missing.

        Two rules:
          1. A FAILED outcome (Poor / Not Done) on a Safety Task Catalog task
             flagged evidence_required=1 must carry an Evidence Photo — a failed
             check escalates to a Maintenance Request, so the failure needs proof.
             A passing outcome is not gated.
          2. A Security-category finding (catalog category, or a finding row
             carrying the same category — best-effort) may not drive escalation
             without an Evidence Photo.
        """
        if self.evidence_photo:
            return

        if self._failed_requires_evidence():
            frappe.throw(
                _("A failed safety task ({0}) on a task that requires evidence "
                  "must carry a photo. Please attach an Evidence Photo before "
                  "submitting.").format(self.execution_status),
                title=_("Evidence Photo Required"),
            )

        if self._has_security_escalation():
            frappe.throw(
                _("A Security-category finding requires photo evidence before it "
                  "can escalate. Please attach an Evidence Photo before submitting."),
                title=_("Evidence Photo Required"),
            )

    def _failed_requires_evidence(self) -> bool:
        """True when a FAILED outcome on an evidence_required task lacks proof.

        The photo is mandated only for a failing result (Poor / Not Done) — the
        same statuses that escalate to a Maintenance Request — so the recorded
        failure can be substantiated."""
        if self.execution_status not in _REPAIR_NEEDED_STATUSES:
            return False
        if not self.task:
            return False
        return bool(
            frappe.db.get_value("Safety Task Catalog", self.task, "evidence_required")
        )

    def _has_security_escalation(self) -> bool:
        """True when a Security-category finding would drive an escalation.

        The Security signal lives on the catalog task's category (the
        department Select, which includes 'Security'); best-effort, a finding
        row carrying the same category word is honoured too. Only actionable
        findings (Issue Type + Room, not Resolved) can escalate."""
        if self._category_is_security():
            if any(_finding_escalates(f) for f in self.findings or []):
                return True
        for finding in self.findings or []:
            if _row_category_is_security(finding) and _finding_escalates(finding):
                return True
        return False

    def _category_is_security(self) -> bool:
        """True when the linked catalog task's category is Security."""
        if not self.task:
            return False
        category = frappe.db.get_value("Safety Task Catalog", self.task, "department")
        return (category or "").strip().lower() == _SECURITY_CATEGORY


def _finding_escalates(finding) -> bool:
    """A finding escalates when it is actionable — the same rule that decides
    whether it spawns a ticket, so escalation and fan-out can never disagree."""
    return is_actionable(finding)


def _row_category_is_security(finding) -> bool:
    """Best-effort: True when a finding row carries a Security category."""
    return (finding.get("finding_category") or "").strip().lower() == _SECURITY_CATEGORY
