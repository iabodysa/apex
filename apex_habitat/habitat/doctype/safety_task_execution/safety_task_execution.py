"""Safety Task Execution controller.

A live execution captures findings observed in the field. On submit it fans out
each actionable finding to one Maintenance Request via the shared
habitat.utils.finding_fanout helper, stamping source_execution on the ticket and
writing the finding's generated_maintenance_request back-link (idempotent).

Validation enforces photo evidence: a catalog task flagged evidence_required
must carry an Evidence Photo, and a Security-category finding must carry one
before it can drive an escalation.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.habitat.utils.finding_fanout import fan_out_findings

# Catalog category (Safety Task Catalog.department) that demands photo evidence
# before a finding may escalate. Matched case-insensitively so a finding-row
# category carrying the same word is honoured too (best-effort, forward-compat).
_SECURITY_CATEGORY = "security"


class SafetyTaskExecution(Document):
    def validate(self):
        self._enforce_evidence()

    def on_submit(self):
        # Each actionable finding spawns one Maintenance Request stamped with
        # source_execution; the finding's generated_maintenance_request back-link
        # is written so a re-run never duplicates a ticket.
        fan_out_findings(self.findings, self)

    # -- validation ---------------------------------------------------------

    def _enforce_evidence(self):
        """Throw a clear English message when required photo evidence is missing.

        Two rules:
          1. If the linked Safety Task Catalog task has evidence_required=1, an
             Evidence Photo is mandatory for the whole execution.
          2. A Security-category finding (catalog category, or a finding row
             carrying the same category — best-effort) may not drive escalation
             without an Evidence Photo.
        """
        if self.evidence_photo:
            return  # a photo is present — both rules are satisfied

        if self._task_requires_evidence():
            frappe.throw(
                _("This safety task requires photo evidence. "
                  "Please attach an Evidence Photo before submitting."),
                title=_("Evidence Photo Required"),
            )

        if self._has_security_escalation():
            frappe.throw(
                _("A Security-category finding requires photo evidence before it "
                  "can escalate. Please attach an Evidence Photo before submitting."),
                title=_("Evidence Photo Required"),
            )

    def _task_requires_evidence(self) -> bool:
        """True when the linked catalog task is flagged evidence_required."""
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
    """A finding escalates when it is actionable: it names an Issue Type and a
    Room and is not already Resolved (mirrors finding_fanout._is_actionable)."""
    if not finding.get("issue_type"):
        return False
    if not finding.get("room"):
        return False
    if (finding.get("status") or "") == "Resolved":
        return False
    return True


def _row_category_is_security(finding) -> bool:
    """Best-effort: True when a finding row carries a Security category."""
    return (finding.get("finding_category") or "").strip().lower() == _SECURITY_CATEGORY
