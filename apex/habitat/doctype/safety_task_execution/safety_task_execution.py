# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.habitat.utils.finding_fanout import fan_out_findings, is_actionable


_SECURITY_CATEGORY = "security"

_REPAIR_NEEDED_STATUSES = ("Poor", "Not Done")


class SafetyTaskExecution(Document):
    def validate(self):
        self._enforce_evidence()

    def on_submit(self):
        fan_out_findings(self.findings, self)
        self._escalate_failed_execution()

    def on_cancel(self):
        frappe.db.set_value(
            "Maintenance Request",
            {"source_execution": self.name, "docstatus": 0, "status": "Open"},
            "status",
            "Closed",
        )

    def _escalate_failed_execution(self) -> None:
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
        mr.insert(ignore_permissions=True)
        self.db_set("linked_maintenance_request", mr.name)

    def _has_linked_request(self) -> bool:
        mr_name = self.linked_maintenance_request
        if not mr_name:
            return False
        return bool(frappe.db.exists("Maintenance Request", mr_name))

    def _scope_room(self) -> str | None:
        for finding in self.findings or []:
            if finding.get("room"):
                return finding.get("room")
        return frappe.db.get_value(
            "Room", {"building": self.building}, "name"
        )

    def _enforce_evidence(self):
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
        if self.execution_status not in _REPAIR_NEEDED_STATUSES:
            return False
        if not self.task:
            return False
        return bool(
            frappe.db.get_value("Safety Task Catalog", self.task, "evidence_required")
        )

    def _has_security_escalation(self) -> bool:
        if self._category_is_security():
            if any(_finding_escalates(f) for f in self.findings or []):
                return True
        for finding in self.findings or []:
            if _row_category_is_security(finding) and _finding_escalates(finding):
                return True
        return False

    def _category_is_security(self) -> bool:
        if not self.task:
            return False
        category = frappe.db.get_value("Safety Task Catalog", self.task, "department")
        return (category or "").strip().lower() == _SECURITY_CATEGORY


def _finding_escalates(finding) -> bool:
    return is_actionable(finding)


def _row_category_is_security(finding) -> bool:
    return (finding.get("finding_category") or "").strip().lower() == _SECURITY_CATEGORY
