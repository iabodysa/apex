"""
Base service class providing common functionality for all services.

Rules:
- Services contain business logic and orchestration.
- Repositories contain persistence and read/write helpers.
- DocType controllers should stay thin and delegate to services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import frappe
from frappe import _

if TYPE_CHECKING:
    from frappe.model.document import Document


class BaseService:
    """Base class for service-layer components."""

    def __init__(self, user: Optional[str] = None):
        self.user = user or frappe.session.user

    def check_permission(
        self,
        doctype: str,
        ptype: str = "read",
        doc: Optional["Document"] = None,
        throw: bool = True,
    ) -> bool:
        """Check the current user's permission."""
        return frappe.has_permission(
            doctype=doctype,
            ptype=ptype,
            doc=doc,
            user=self.user,
            throw=throw,
        )

    def validate_mandatory(self, data: dict[str, Any], fields: list[str]) -> None:
        """Validate that mandatory fields are present."""
        missing = [f for f in fields if not data.get(f)]
        if missing:
            frappe.throw(_("Missing required fields: {0}").format(", ".join(missing)))

