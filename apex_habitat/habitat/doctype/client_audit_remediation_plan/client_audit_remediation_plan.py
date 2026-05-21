"""Client Audit Remediation Plan controller."""

from __future__ import annotations

from frappe.model.document import Document


class ClientAuditRemediationPlan(Document):
    def before_save(self):
        # Validate document properties
        if not self.doctype:
            return
