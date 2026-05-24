"""Safety Task Execution controller."""

from __future__ import annotations

from frappe.model.document import Document


class SafetyTaskExecution(Document):
    pass


def before_save(doc, method=None):
    pass
