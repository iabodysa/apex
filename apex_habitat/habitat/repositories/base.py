"""
Base repository class for data access operations.

Rules:
- Repositories never contain business logic.
- Prefer small, explicit read helpers over broad "get_doc everywhere".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar

import frappe

if TYPE_CHECKING:
    from frappe.model.document import Document

T = TypeVar("T", bound="Document")


class BaseRepository(Generic[T]):
    """Base class for repository-layer components."""

    doctype: str = ""

    def __init__(self):
        if not self.doctype:
            raise ValueError("Repository must define doctype attribute")

    def exists(self, name: str) -> bool:
        return bool(frappe.db.exists(self.doctype, name))

    def get(self, name: str, for_update: bool = False) -> Optional[T]:
        if not self.exists(name):
            return None
        return frappe.get_doc(self.doctype, name, for_update=for_update)

    def get_or_throw(self, name: str, for_update: bool = False) -> T:
        doc = self.get(name, for_update=for_update)
        if not doc:
            frappe.throw(f"{self.doctype} {name} not found")
        return doc

    def get_value(self, name: str, fieldname: str | list[str]) -> Any:
        return frappe.db.get_value(self.doctype, name, fieldname)

