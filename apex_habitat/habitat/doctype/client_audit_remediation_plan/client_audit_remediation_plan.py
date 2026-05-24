"""Client Audit Remediation Plan controller."""

from __future__ import annotations

from frappe.model.document import Document


class ClientAuditRemediationPlan(Document):
    pass


def before_save(doc, method=None):
    # Validate document properties
    if not doc.doctype:
        return
